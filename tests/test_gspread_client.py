import pytest
import sys
import os
import tempfile
import csv

# Add the project root to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stnd.utility.logger import make_gspread_client


class TestGspreadClient:
    """Test the GspreadClient functionality with real Google Sheets"""

    @pytest.fixture
    def gspread_client(self):
        """Create a GspreadClient instance for testing"""

        # Create a mock logger object with basic logging
        class MockLogger:
            def log_or_print(self, message, level="INFO"):
                print(f"[{level}] {message}")

        logger = MockLogger()
        client = make_gspread_client(logger)
        return client

    def _create_test_csv(self, column_b_value):
        """Helper function to create a temporary CSV file with test data"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_csv:
            csv_path = tmp_csv.name
            writer = csv.writer(tmp_csv)
            writer.writerow(["Column A", "Column B"])
            writer.writerow(["value 1", column_b_value])
        return csv_path

    def test_gspread_update_and_get(self, gspread_client):
        """Test updating a spreadsheet and getting values from it using upload_csvs_to_spreadsheet"""
        # Spreadsheet URL provided by the user
        spreadsheet_url = "https://docs.google.com/spreadsheets/d/1BIuFVOpXays2NEj5P2hPCJXhsL9lSqeOU10fzsPiUUs/edit?usp=sharing"
        worksheet_name = "Worksheet_1"

        # Get the spreadsheet and worksheet to check initial value
        spreadsheet = gspread_client.get_spreadsheet_by_url(spreadsheet_url)
        worksheet = spreadsheet.worksheet(worksheet_name)

        # Initial test: Get current value at B2
        initial_value = worksheet.acell("B2").value
        print(f"Initial value at B2: {initial_value}")

        # Verify the initial expected value
        assert (
            initial_value == "value 2"
        ), f"Expected 'value 2' but got '{initial_value}'"

        # Create a temporary CSV file for first update
        csv_path_1 = self._create_test_csv("test_value_1")

        # Update spreadsheet using upload_csvs_to_spreadsheet
        gspread_client.upload_csvs_to_spreadsheet(
            spreadsheet_url, [csv_path_1], worksheet_names=[worksheet_name]
        )

        # Get the value again to verify the update
        updated_value_1 = worksheet.acell("B2").value
        print(f"Updated value at B2: {updated_value_1}")
        assert (
            updated_value_1 == "test_value_1"
        ), f"Expected 'test_value_1' but got '{updated_value_1}'"

        # Create a temporary CSV file for second update
        csv_path_2 = self._create_test_csv("test_value_2")

        # Update spreadsheet again using upload_csvs_to_spreadsheet
        gspread_client.upload_csvs_to_spreadsheet(
            spreadsheet_url, [csv_path_2], worksheet_names=[worksheet_name]
        )

        # Get the value again to verify the second update
        updated_value_2 = worksheet.acell("B2").value
        print(f"Second updated value at B2: {updated_value_2}")
        assert (
            updated_value_2 == "test_value_2"
        ), f"Expected 'test_value_2' but got '{updated_value_2}'"

        # Create a temporary CSV file to restore original value
        csv_path_restore = self._create_test_csv(initial_value)

        # Restore the original value
        gspread_client.upload_csvs_to_spreadsheet(
            spreadsheet_url,
            [csv_path_restore],
            worksheet_names=[worksheet_name],
        )

        restored_value = worksheet.acell("B2").value
        assert (
            restored_value == initial_value
        ), f"Failed to restore original value"
        print(f"Successfully restored original value: {restored_value}")

        # Clean up temporary CSV files
        if os.path.exists(csv_path_1):
            os.unlink(csv_path_1)
        if os.path.exists(csv_path_2):
            os.unlink(csv_path_2)
        if os.path.exists(csv_path_restore):
            os.unlink(csv_path_restore)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
