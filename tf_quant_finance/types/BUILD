# Typing utilities

# Placeholder: load py_library

package(
    default_visibility = ["//tf_quant_finance:__subpackages__"],
    licenses = ["notice"],
)

py_library(
    name = "types",
    srcs = ["__init__.py"],
    srcs_version = "PY3",
    deps = [
        ":data_types",
    ],
)

py_library(
    name = "data_types",
    srcs = ["data_types.py"],
    srcs_version = "PY3",
    deps = [
        "//tf_quant_finance/datetime",
        # numpy dep,
        # tensorflow dep,
    ],
)
