import os
import tempfile
from unittest.mock import MagicMock, patch


# Targets under test
from stnd.utility.logger import sync_local_file_with_gdrive, make_gdrive_client


class TestSyncLocalFileWithGdrive:
    """Unit tests for sync_local_file_with_gdrive (Google Drive helpers)."""

    def test_upload_flow_calls_setcontent_and_upload(self):
        # Arrange: create a temp local file to "upload"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            local_path = tmp.name
            tmp.write("hello world")

        gdrive_client = MagicMock()
        remote_url = "https://drive.google.com/file/d/FAKE-ID/view"

        # Remote file mock (no mimeType key so type assertion branch is skipped)
        remote_file = MagicMock()
        remote_file.__contains__.return_value = (
            False  # "mimeType" not in remote_file
        )

        with patch(
            "stnd.utility.logger.get_gdrive_file_by_url",
            return_value=remote_file,
        ) as mocked_get:
            # Act
            result = sync_local_file_with_gdrive(
                gdrive_client,
                local_path,
                remote_url,
                download=False,
                logger=None,
            )

        # Assert
        mocked_get.assert_called_once_with(gdrive_client, remote_url)
        remote_file.SetContentFile.assert_called_once_with(local_path)
        remote_file.Upload.assert_called_once_with()
        assert result is remote_file

        # Cleanup
        if os.path.exists(local_path):
            os.unlink(local_path)

    def test_download_flow_calls_getcontentfile(self):
        # Arrange: path to download into
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            download_path = tmp.name

        # Ensure file is removed so we can observe re-write by GetContentFile
        if os.path.exists(download_path):
            os.unlink(download_path)

        gdrive_client = MagicMock()
        remote_url = "https://drive.google.com/file/d/FAKE-ID/view"

        remote_file = MagicMock()
        remote_file.__contains__.return_value = False  # skip mimeType check

        with patch(
            "stnd.utility.logger.get_gdrive_file_by_url",
            return_value=remote_file,
        ) as mocked_get:
            # Act
            result = sync_local_file_with_gdrive(
                gdrive_client,
                download_path,
                remote_url,
                download=True,
                logger=None,
            )

        # Assert
        mocked_get.assert_called_once_with(gdrive_client, remote_url)
        remote_file.GetContentFile.assert_called_once_with(download_path)
        assert result is remote_file

        # Cleanup
        if os.path.exists(download_path):
            os.unlink(download_path)

    def test_download_update_and_restore_real_remote_file(self):
        # Arrange: create a real gdrive client using service account credentials
        class MockLogger:
            def log_or_print(self, message, level="INFO"):
                pass

        logger = MockLogger()
        gdrive_client = make_gdrive_client(logger)

        # Provided public file URL containing "Hello world!"
        remote_url = "https://drive.google.com/file/d/1sKy4qajDHEHa8irdZdnIghWk3oSb1zd0/view?usp=sharing"

        # Temp file paths
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            local_path = tmp.name
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp2:
            verify_path = tmp2.name

        # try:
        # Step 1: Download original content
        sync_local_file_with_gdrive(
            gdrive_client, local_path, remote_url, download=True, logger=logger
        )
        with open(local_path, "r") as f:
            original_content = f.read()

        # Sanity check the original matches current expectation
        assert original_content.strip() == "Hello world!"

        # Step 2: Update remote with new content
        new_content = "Hello updated world!"
        with open(local_path, "w") as f:
            f.write(new_content)
        sync_local_file_with_gdrive(
            gdrive_client, local_path, remote_url, download=False, logger=logger
        )

        # Verify remote reflects the update by downloading to a different path
        sync_local_file_with_gdrive(
            gdrive_client, verify_path, remote_url, download=True, logger=logger
        )
        with open(verify_path, "r") as f:
            updated_content = f.read()
        assert updated_content == new_content

        # Step 3: Restore original content
        with open(local_path, "w") as f:
            f.write(original_content)
        sync_local_file_with_gdrive(
            gdrive_client, local_path, remote_url, download=False, logger=logger
        )

        # Verify restore
        sync_local_file_with_gdrive(
            gdrive_client, verify_path, remote_url, download=True, logger=logger
        )
        with open(verify_path, "r") as f:
            restored = f.read()
        assert restored == original_content
        # finally:
        for p in (local_path, verify_path):
            if os.path.exists(p):
                os.unlink(p)
