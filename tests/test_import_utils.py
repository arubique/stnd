import pytest
import sys
import os
import importlib
import importlib.util
from unittest.mock import Mock, patch, MagicMock
from types import ModuleType

# Add the project root to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stnd.utility.imports import (
    LazyModuleWrapper,
    is_bulitin_name,
    importlib_lazy_import,
    lazy_import,
    _LazyModule,
    make_lazy_module,
    pop_all_modules_by_filter,
    import_from_string,
    make_from_class_ctor,
    update_enums_in_config,
    PACKAGE_SEPARATOR,
    FROM_CLASS_KEY,
)


class TestLazyModuleWrapper:
    """Test the LazyModuleWrapper class"""

    def test_init(self):
        """Test LazyModuleWrapper initialization"""
        wrapper = LazyModuleWrapper("os")
        assert wrapper.module_name == "os"
        assert wrapper.module is None
        assert "__spec__" in wrapper.default_attrs
        assert "__name__" in wrapper.default_attrs

    def test_try_to_import(self):
        """Test the try_to_import method"""
        wrapper = LazyModuleWrapper("os")
        original_modules = sys.modules.copy()

        # Test that module gets imported and stored
        wrapper.try_to_import()
        assert wrapper.module is not None
        assert hasattr(wrapper.module, "path")

        # Clean up
        sys.modules.clear()
        sys.modules.update(original_modules)

    def test_getattr_builtin_name(self):
        """Test __getattr__ with builtin names"""
        wrapper = LazyModuleWrapper("os")

        # Builtin names should not trigger import
        result = wrapper.__getattr__("__name__")
        assert result == "os"
        assert wrapper.module is None  # Should not have imported yet

    def test_getattr_non_builtin_name(self):
        """Test __getattr__ with non-builtin names"""
        wrapper = LazyModuleWrapper("os")
        original_modules = sys.modules.copy()

        # Non-builtin names should trigger import
        result = wrapper.__getattr__("path")
        assert result is not None
        assert wrapper.module is not None

        # Clean up
        sys.modules.clear()
        sys.modules.update(original_modules)


class TestIsBuiltinName:
    """Test the is_bulitin_name function"""

    def test_builtin_names(self):
        """Test that builtin names are correctly identified"""
        assert is_bulitin_name("__name__") == True
        assert is_bulitin_name("__file__") == True
        assert is_bulitin_name("__spec__") == True
        assert is_bulitin_name("__doc__") == True

    def test_non_builtin_names(self):
        """Test that non-builtin names are correctly identified"""
        assert is_bulitin_name("path") == False
        assert is_bulitin_name("os") == False
        assert is_bulitin_name("__") == False  # Too short
        assert is_bulitin_name("_name_") == False  # Wrong format
        assert is_bulitin_name("name__") == False  # Wrong format


class TestImportlibLazyImport:
    """Test the importlib_lazy_import function"""

    def test_lazy_import(self):
        """Test lazy import functionality"""
        original_modules = sys.modules.copy()

        # Test importing a standard module
        module = importlib_lazy_import("os")
        assert isinstance(module, ModuleType)
        assert module.__name__ == "os"
        assert "os" in sys.modules

        # Clean up
        sys.modules.clear()
        sys.modules.update(original_modules)


class TestLazyImport:
    """Test the lazy_import function"""

    def test_lazy_import_wrapper(self):
        """Test that lazy_import returns a LazyModuleWrapper"""
        original_modules = sys.modules.copy()

        module = lazy_import("os")
        assert isinstance(module, LazyModuleWrapper)
        assert module.module_name == "os"
        assert "os" in sys.modules

        # Clean up
        sys.modules.clear()
        sys.modules.update(original_modules)


class TestLazyModule:
    """Test the _LazyModule class"""

    def test_init(self):
        """Test _LazyModule initialization"""
        import_structure = {
            "submodule1": ["Class1", "function1"],
            "submodule2": ["Class2", "function2"],
        }

        lazy_module = _LazyModule(
            "test_module", "/path/to/module.py", import_structure
        )

        assert lazy_module._name == "test_module"
        assert lazy_module._modules == {"submodule1", "submodule2"}
        assert lazy_module._class_to_module["Class1"] == "submodule1"
        assert lazy_module._class_to_module["function1"] == "submodule1"
        assert "Class1" in lazy_module.__all__
        assert "function1" in lazy_module.__all__

    def test_dir(self):
        """Test the __dir__ method"""
        import_structure = {"submodule1": ["Class1"]}
        lazy_module = _LazyModule(
            "test_module", "/path/to/module.py", import_structure
        )

        dir_result = lazy_module.__dir__()
        assert "submodule1" in dir_result
        assert "Class1" in dir_result

    def test_getattr_objects(self):
        """Test __getattr__ with objects"""
        extra_objects = {"test_obj": "test_value"}
        lazy_module = _LazyModule(
            "test_module", "/path/to/module.py", {}, extra_objects=extra_objects
        )

        result = lazy_module.__getattr__("test_obj")
        assert result == "test_value"

    def test_getattr_nonexistent(self):
        """Test __getattr__ with nonexistent attribute"""
        lazy_module = _LazyModule("test_module", "/path/to/module.py", {})

        with pytest.raises(AttributeError):
            lazy_module.__getattr__("nonexistent")

    def test_reduce(self):
        """Test the __reduce__ method"""
        import_structure = {"submodule1": ["Class1"]}
        lazy_module = _LazyModule(
            "test_module", "/path/to/module.py", import_structure
        )

        reduce_result = lazy_module.__reduce__()
        assert reduce_result[0] == _LazyModule
        assert reduce_result[1] == (
            "test_module",
            "/path/to/module.py",
            import_structure,
        )


class TestMakeLazyModule:
    """Test the make_lazy_module function"""

    def test_make_lazy_module(self):
        """Test make_lazy_module function"""
        import_structure = {"submodule1": ["Class1"]}

        lazy_module = make_lazy_module(
            "test_module", "/path/to/module.py", import_structure
        )

        assert isinstance(lazy_module, _LazyModule)
        assert lazy_module._name == "test_module"


class TestPopAllModulesByFilter:
    """Test the pop_all_modules_by_filter function"""

    def test_pop_modules_with_filter(self):
        """Test popping modules with a filter condition"""
        # Add some test modules to sys.modules
        original_modules = sys.modules.copy()
        sys.modules["test_module1"] = Mock()
        sys.modules["test_module2"] = Mock()
        sys.modules["other_module"] = Mock()

        # Filter function to match test modules
        def filter_condition(name):
            return name.startswith("test_")

        # Mock the error_or_print function
        with patch(
            "stnd.utility.imports.error_or_print"
        ) as mock_error_or_print:
            removed_modules = pop_all_modules_by_filter(filter_condition)

        # Check that test modules were removed
        assert "test_module1" not in sys.modules
        assert "test_module2" not in sys.modules
        assert "other_module" in sys.modules  # Should remain
        assert "test_module1" in removed_modules
        assert "test_module2" in removed_modules

        # Clean up
        sys.modules.clear()
        sys.modules.update(original_modules)

    def test_pop_modules_with_filter_name(self):
        """Test popping modules with custom filter name"""
        original_modules = sys.modules.copy()
        sys.modules["test_module1"] = Mock()

        def filter_condition(name):
            return name.startswith("test_")

        with patch(
            "stnd.utility.imports.error_or_print"
        ) as mock_error_or_print:
            removed_modules = pop_all_modules_by_filter(
                filter_condition, filter_name="test modules"
            )

        # Check that the custom filter name was used
        mock_error_or_print.assert_called_once()
        call_args = mock_error_or_print.call_args[0][0]
        assert "test modules" in call_args

        # Clean up
        sys.modules.clear()
        sys.modules.update(original_modules)


class TestImportFromString:
    """Test the import_from_string function"""

    def test_import_simple_module(self):
        """Test importing a simple module"""
        result = import_from_string("os")
        assert result is not None
        assert hasattr(result, "path")

    def test_import_with_nested_attrs(self):
        """Test importing with nested attributes"""
        result = import_from_string("os.path", nested_attrs_depth=1)
        assert result is not None
        assert hasattr(result, "join")

    def test_import_with_reload(self):
        """Test importing with reload=True"""
        # First import
        result1 = import_from_string("os")
        # Import again with reload
        result2 = import_from_string("os", reload=True)
        assert result1 is not None
        assert result2 is not None

    def test_import_nonexistent_module(self):
        """Test importing a nonexistent module"""
        with pytest.raises(ImportError):
            import_from_string("nonexistent_module_12345")


class TestMakeFromClassCtor:
    """Test the make_from_class_ctor function"""

    def test_make_from_class_ctor_simple(self):
        """Test creating constructor with simple config"""
        from_class_config = {
            "class": "builtins.dict",
            "kwargs": {"key1": "value1"},
        }

        result = make_from_class_ctor(from_class_config)
        assert isinstance(result, dict)
        assert result["key1"] == "value1"

    def test_make_from_class_ctor_with_pos_args(self):
        """Test creating constructor with positional arguments"""
        from_class_config = {"class": "builtins.list", "kwargs": {}}

        # list() constructor takes an iterable, so we pass a single list argument
        result = make_from_class_ctor(
            from_class_config, pos_args_list=[[1, 2, 3]]
        )
        assert isinstance(result, list)
        assert result == [1, 2, 3]

    def test_make_from_class_ctor_with_importable_kwargs(self):
        """Test creating constructor with importable kwargs"""
        from_class_config = {
            "class": "builtins.dict",
            "kwargs": {"key1": "value1"},
            "kwargs_to_import": {"os_module": "os"},
        }

        result = make_from_class_ctor(from_class_config)
        assert isinstance(result, dict)
        assert result["key1"] == "value1"
        assert hasattr(result["os_module"], "path")

    def test_make_from_class_ctor_missing_class(self):
        """Test creating constructor with missing class key"""
        from_class_config = {"kwargs": {"key1": "value1"}}

        with pytest.raises(Exception):
            make_from_class_ctor(from_class_config)


class TestUpdateEnumsInConfig:
    """Test the update_enums_in_config function"""

    def test_update_enums_simple(self):
        """Test updating enums in config"""
        config = {"enum1": "os", "enum2": "sys", "regular_key": "value"}

        result = update_enums_in_config(config, ["enum1", "enum2"])

        assert hasattr(result["enum1"], "path")  # os module
        assert hasattr(result["enum2"], "path")  # sys module
        assert result["regular_key"] == "value"  # Should remain unchanged

    def test_update_enums_nested(self):
        """Test updating enums with nested attributes"""
        config = {"enum1": "os.path"}

        result = update_enums_in_config(config, ["enum1"], nested_attrs_depth=2)

        assert hasattr(result["enum1"], "join")  # os.path.join

    def test_update_enums_non_string(self):
        """Test updating enums with non-string values"""
        config = {"enum1": 123, "enum2": "os"}  # Not a string

        with pytest.raises(AssertionError):
            update_enums_in_config(config, ["enum1", "enum2"])

    def test_update_enums_deep_copy(self):
        """Test that original config is not modified"""
        original_config = {"enum1": "os", "regular_key": "value"}

        result = update_enums_in_config(original_config, ["enum1"])

        # Original should still be string
        assert original_config["enum1"] == "os"
        # Result should be module
        assert hasattr(result["enum1"], "path")


class TestConstants:
    """Test module constants"""

    def test_package_separator(self):
        """Test PACKAGE_SEPARATOR constant"""
        assert PACKAGE_SEPARATOR == "."

    def test_from_class_key(self):
        """Test FROM_CLASS_KEY constant"""
        assert FROM_CLASS_KEY == "from_class"


# Integration tests
class TestIntegration:
    """Integration tests for the imports module"""

    def test_lazy_import_workflow(self):
        """Test complete lazy import workflow"""
        original_modules = sys.modules.copy()

        # Test lazy import
        lazy_os = lazy_import("os")
        assert isinstance(lazy_os, LazyModuleWrapper)

        # Access attribute to trigger import
        path_attr = lazy_os.path
        assert path_attr is not None

        # Clean up
        sys.modules.clear()
        sys.modules.update(original_modules)

    def test_lazy_module_workflow(self):
        """Test complete lazy module workflow"""
        import_structure = {"submodule1": ["Class1", "function1"]}

        lazy_module = make_lazy_module(
            "test_module", "/path/to/module.py", import_structure
        )

        # Test that the module is properly configured
        assert "submodule1" in lazy_module._modules
        assert "Class1" in lazy_module._class_to_module
        assert "function1" in lazy_module._class_to_module


if __name__ == "__main__":
    pytest.main([__file__])
