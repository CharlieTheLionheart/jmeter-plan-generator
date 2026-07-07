"""Cross-module helpers: XML building and Groovy preprocessor snippets."""

from utils.preprocessor_helpers import (
    PreprocessorHelperError,
    all_groovy_decls,
    build_device_identifier,
    calculate_device_number,
    calculate_timestamps,
    clone_rows,
    groovy_calculate_device_number_decl,
    groovy_calculate_timestamps_decl,
    groovy_clone_rows_decl,
    groovy_device_identifier_decl,
)

__all__ = [
    "PreprocessorHelperError",
    "all_groovy_decls",
    "build_device_identifier",
    "calculate_device_number",
    "calculate_timestamps",
    "clone_rows",
    "groovy_calculate_device_number_decl",
    "groovy_calculate_timestamps_decl",
    "groovy_clone_rows_decl",
    "groovy_device_identifier_decl",
]
