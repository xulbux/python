# x-tools:file[unlisted,update]

"""
Shared constants, file extensions, and auto-ignore rules for CLI tools.
"""

import fnmatch
import re
from typing import Literal

# ****************************************************** FILE EXTENSIONS ******************************************************

# fmt: off
ARCHIVE_EXTS: frozenset[str] = frozenset({
    "7z", "apk", "asar", "bz2", "cab", "cpio", "deb", "dmg", "ear", "gz", "iso", "jar", "lz", "lz4", "lzma", "npz", "pak",
    "phar", "rar", "rpm", "sigzip", "snap", "squashfs", "tar", "tbz2", "tgz", "txz", "tzst", "war", "whl", "xz", "z", "zip",
    "zst"
})
"""Extensions of archive and compressed container files."""
AUDIO_EXTS: frozenset[str] = frozenset({
    "aac", "aif", "aiff", "alac", "amr", "ape", "au", "caf", "cfa", "flac", "m4a", "mid", "midi", "mka", "mp3", "oga", "ogg",
    "opus", "voc", "wav", "wma", "wv"
})
"""Extensions of audio recordings and sound files."""
CODE_EXTS: frozenset[str] = frozenset({
    "ahk", "apache", "applescript", "appxmanifest", "asm", "asp", "aspx", "astro", "awk", "bash", "bash_logout",
    "bash_profile", "bashrc", "bat", "bib", "bicep", "blocklist", "browserslistrc", "bsd", "c", "cfg", "cjs", "clj", "cljc",
    "cljs", "cmake", "code-snippets", "code-workspace", "code_snippets", "code_workspace", "colors", "conf", "config", "cpp",
    "cr", "cs", "csh", "csproj", "css", "cts", "cu", "cursorignore", "d", "dart", "def", "defs", "desktop", "diff",
    "directory", "dirs", "dockerfile", "dockerignore", "editorconfig", "edn", "ejs", "el", "env", "env.example", "env.local",
    "env.staging", "env.testing", "erb", "erl", "eslintignore", "ex", "exs", "f", "f90", "f95", "fbs", "filters", "fish",
    "flow", "frag", "fs", "fsi", "fst", "fsx", "g4", "gd", "gitattributes", "gitconfig", "gitignore", "gitkeep", "gitmodules",
    "gleam", "glsl", "glslfx", "go", "gql", "gradle", "graphql", "groovy", "gtkrc-2.0", "gtkrc-3.0", "gyp", "gypi", "h", "hbs",
    "hcl", "hintrc", "hjson", "hpp", "hs", "htaccess", "htm", "html", "html5", "http", "hx", "idl", "inc", "ini", "install",
    "ipynb", "j2", "jade", "java", "jinja", "jl", "js", "json", "json5", "jsonc", "jsonl", "jsx", "kml", "ksh", "kt", "kts",
    "lark", "less", "library-ms", "licence", "license", "liquid", "lisp", "list", "locale", "lock", "lua", "m", "make",
    "manifest", "mdc", "mdl", "mdx", "menu", "meta", "metal", "mjs", "ml", "mli", "mm", "mod", "mojo", "msrv", "mtlx", "mts",
    "ndjson", "nim", "nims", "nix", "nmake", "npmignore", "npmrc", "nvmrc", "nxignore", "odin", "osl", "pas", "patch",
    "pbxproj", "pc", "php", "pl", "plist", "pm", "po", "pod", "policy", "pom", "pot", "prefs", "preset", "prettierignore",
    "prettierrc", "prf", "prisma", "pro", "profile", "proj", "properties", "props", "proto", "ps", "ps1", "ps1xml", "psd1",
    "psm1", "pubxml", "pug", "pxd", "pxi", "py", "pyf", "pyi", "pypirc", "pyw", "pyx", "qml", "qmltypes", "r", "rb", "rc",
    "ron", "rs", "rsp", "rules", "s", "sass", "sc", "scala", "scss", "sct", "security", "sed", "setting", "sh", "sln", "sol",
    "spdx", "sql", "srcinfo", "srx", "sty", "styl", "sum", "svelte", "svg", "swift", "tcl", "template", "tern-project", "tex",
    "tf", "tfvars", "theme", "tmLanguage", "tmpl", "toml", "tpl", "translation_io", "ts", "tsx", "typ", "typed", "url", "v",
    "vader", "vbs", "vcxproj", "vert", "vimrc", "vscodeignore", "vue", "webmanifest", "wgsl", "winprf", "wixproj", "wxs",
    "xaml", "xbel", "xml", "xmp", "xsd", "xsl", "xslt", "yaml", "yapf", "yml", "zig", "zprofile", "zsh", "zshrc"
})
"""Extensions of programming language source code and structured configuration files."""
DATA_EXTS: frozenset[str] = frozenset({
    "accdb", "aishm", "ani", "arm", "arm64", "bdic", "bf", "binarypb", "binpb", "blf", "certs", "cff", "cnpf", "comp", "count",
    "crt", "csv", "cube", "cube-shaperlut", "cube_shaperlut", "dat", "dat-shaperlut", "dat_shaperlut", "dat-shm", "dat-wal",
    "data", "db", "db-journal", "db-shm", "db-wal", "db3", "dctl", "deflate", "dpb1", "dpx", "drfx", "drp", "fdb", "file",
    "fingerprint", "fudict", "fuse", "gdb", "gpg", "hdr", "id", "idb", "ilut", "ind", "index", "inf", "inp", "int", "iolut",
    "jfc", "key", "keyring", "keystore", "knsregistry", "kwl", "ldb", "localstorage", "localstorage-shm", "localstorage-wal",
    "map", "mdb", "metainfo", "nbt", "ocio", "ofx", "ograf", "olut", "parquet", "pb", "pem", "plugin", "ppk", "prin", "pt",
    "ptb", "pth", "pub", "rdb", "real", "regtrans-ms", "safetensors", "salt", "sdb", "search-ms", "spi1d", "sqlite",
    "sqlite-journal", "sqlite-shm", "sqlite-wal", "sqlite3", "tag", "tflite", "token", "tsv", "usda", "vscdb"
})
"""Extensions of database, binary data, key, certificate, and lookup files."""
DOC_EXTS: frozenset[str] = frozenset({
    "azw", "azw3", "djvu", "doc", "docb", "docm", "docx", "dot", "dotm", "dotx", "dq", "eml", "epub", "gddoc", "gdoc", "gdraw",
    "gdslides", "gform", "gjam", "gmap", "gsheet", "gsite", "gslides", "gtable", "md", "mkd", "mobi", "mpp", "mpt", "odt",
    "one", "onepkg", "org", "pages", "pdf", "potm", "potx", "ppam", "pps", "ppsm", "ppsx", "ppt", "pptm", "pptx", "rst", "rtf",
    "sldm", "sldx", "txt", "vdx", "vsd", "vsdx", "vss", "vssx", "vst", "vstx", "vsw", "vsx", "vtx", "wbk", "xla", "xlam",
    "xll", "xls", "xlsb", "xlsm", "xlsx", "xlt", "xltm", "xltx", "xlw"
})
"""Extensions of document, spreadsheet, presentation, and prose files."""
EXEC_EXTS: frozenset[str] = frozenset({
    "appimage", "bin", "cmd", "com", "exe", "msi", "run", "vsix"
})
"""Extensions of executable files and application installers."""
FONT_EXTS: frozenset[str] = frozenset({
    "afm", "bdf", "eot", "fnt", "fon", "otf", "pcf", "pfa", "pfb", "sfd", "ttf", "ufm", "woff", "woff2"
})
"""Extensions of vector and bitmap font asset files."""
IMAGE_EXTS: frozenset[str] = frozenset({
    "ai", "arw", "avif", "bmp", "cr2", "cur", "diricon", "dng", "emf", "eps", "exr", "ggr", "gif", "heic", "icns", "ico",
    "indd", "jpeg", "jpg", "jxl", "kra", "nef", "orf", "pbm", "pgm", "png", "ppm", "psd", "psp", "raw", "rw2", "sr2", "tif",
    "tiff", "webp", "xbm", "xcf"
})
"""Extensions of raster, vector, and raw image asset files."""
STALE_EXTS: frozenset[str] = frozenset({
    "alt", "backup", "bak", "bash_history", "bck", "beta", "bkp", "cache", "disabled", "gotemp", "keep", "last", "lesshst",
    "log", "log0", "log1", "log2", "log3", "log4", "log5", "log6", "log7", "log8", "log9", "msbak", "node_repl_history",
    "obsolete", "off", "old", "orig", "pacnew", "pacsave", "python_history", "stderr", "swo", "swp", "tbcache", "tmp", "temp",
    "trashinfo", "tsbuildinfo", "viminfo", "winprf_backup", "zsh_history"
})
"""Extensions of backup, cache, log, history, and temporary swap files."""
VIDEO_EXTS: frozenset[str] = frozenset({
    "3g2", "3gp", "amv", "asf", "avi", "braw", "dv", "f4v", "flv", "m2ts", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "ogv",
    "r3d", "rm", "rmvb", "vob", "webm", "wmv"
})
"""Extensions of video and motion picture media files."""
NON_TEXT_EXTS: frozenset[str] = ARCHIVE_EXTS | AUDIO_EXTS | IMAGE_EXTS | VIDEO_EXTS | frozenset({
    "3dl", "3ds", "a", "accdb", "aegraphic", "aff", "aishm", "ani", "appimage", "azw", "azw3", "bak", "bdic", "beam", "bin",
    "binarypb", "binpb", "blend", "blf", "cdxml", "cff", "class", "cnpf", "com", "compositefont", "ctb", "cti", "cube",
    "cube-shaperlut", "cube_shaperlut", "dae", "dat", "dat-shaperlut", "dat-shm", "dat-wal", "dat_shaperlut", "data", "db",
    "db-journal", "db-shm", "db-wal", "db3", "dbf", "dcm", "dectest", "deflate", "der", "desklink", "dic", "dict", "djvu",
    "dll", "doc", "docb", "docm", "docx", "dot", "dotm", "dotx", "dpapi", "dpb1", "dpx", "dq", "drfx", "drp", "dylib", "elc",
    "enc", "eot", "epr", "epub", "eve", "exe", "exv", "fbx", "fdb", "flt", "fnt", "fon", "frm", "fudict", "gch", "gdb", "gir",
    "glb", "glox", "gltf", "gpd", "gpg", "hdr", "ibd", "idb", "iges", "ilut", "img", "iolut", "jfc", "jks", "jsxbin",
    "keyring", "keystore", "knsregistry", "ko", "kwl", "kys", "ldb", "lib", "lnk", "localstorage", "localstorage-shm",
    "localstorage-wal", "lock", "luac", "lut", "map", "max", "mb", "mdb", "mha", "mhd", "mobi", "mof", "mogrt", "mpp", "mpt",
    "msc", "msg", "msi", "mtlx", "mts", "mwb", "myd", "myi", "nbt", "ndf", "nii", "node", "npy", "nrrd", "o", "obj", "ocio",
    "ods", "odt", "ofx", "ograf", "olut", "one", "onepkg", "opt", "otf", "ova", "ovf", "p12", "pages", "parquet", "pb", "pcf",
    "pch", "pdb", "pdf", "pfb", "pfx", "pimx", "ply", "pot", "potm", "potx", "ppam", "pps", "ppsm", "ppsx", "ppt", "pptm",
    "pptx", "prcolorstyle", "prfpset", "prin", "propertymap", "prproj", "pt", "ptb", "pth", "pyc", "pyd", "pyo", "qcow2",
    "qmltypes", "rbs", "rdb", "regtrans-ms", "resw", "rnd", "rtf", "safetensors", "salt", "sb3", "schem", "sdb", "sfd", "sldm",
    "sldx", "so", "so.0", "so.1", "so.2", "so.3", "so.4", "so.5", "so.6", "so.7", "so.8", "so.9", "spi1d", "spi3d", "sprite3",
    "sqpreset", "sqlite", "sqlite-journal", "sqlite-shm", "sqlite-wal", "sqlite3", "step", "stl", "stringmap", "swo", "swp",
    "tflite", "tga", "thmx", "tlb", "ttf", "uasset", "ufm", "umap", "usda", "usdc", "usdz", "variablemap", "vdi", "vdx",
    "vhdx", "vmdk", "vscdb", "vsd", "vsdx", "vsix", "vss", "vssx", "vst", "vstx", "vsw", "vsx", "vtp", "vtu", "vtx", "wasm",
    "wbk", "woff", "woff2", "xcl", "xla", "xlam", "xlb", "xll", "xls", "xlsb", "xlsm", "xlsx", "xlt", "xltm", "xltx", "xlw",
    "xrm-ms", "zwc"
})
"""Extensions of true binaries and verbose machine-generated formats that are not source code."""
# fmt: on

type Category = Literal["archive", "audio", "code", "data", "doc", "exec", "font", "image", "stale", "video"]
"""Enumeration of recognized file categories."""

ALL_CATEGORIES: dict[Category, frozenset[str]] = {
    "archive": ARCHIVE_EXTS,
    "audio": AUDIO_EXTS,
    "code": CODE_EXTS,
    "data": DATA_EXTS,
    "doc": DOC_EXTS,
    "exec": EXEC_EXTS,
    "font": FONT_EXTS,
    "image": IMAGE_EXTS,
    "stale": STALE_EXTS,
    "video": VIDEO_EXTS,
}
"""Mapping of category names to sets of member file extensions."""

EXT_TO_CAT: dict[str, Category] = {ext: cat for cat, exts in ALL_CATEGORIES.items() for ext in exts}
"""Mapping of lowercase file extensions directly to their respective category name."""

# ***************************************************** AUTO-IGNORE RULES *****************************************************

# fmt: off
AUTO_IGNORE_FOLDERS: frozenset[str] = frozenset({
    "__pycache__.*", "__pycache__", "__pypackages__.*", "__pypackages__", "__tests__.*", "__tests__", "_locales", "_site",
    ".adobe", ".angular", ".archive-unpack", ".cache", ".codeium", ".coverage", ".fleet", ".git", ".gitlab", ".gradle",
    ".hg", ".idea", ".ipynb_checkpoints", ".kube", ".minecraft/assets/objects", ".minecraft/assets/skins", ".mvn",
    ".mypy_*", ".next", ".npm", ".nuxt", ".nvm", ".nx", ".output", ".pnpm", ".pytest_*", ".ruff_*", ".scannerwork",
    ".sonar", ".styleLintCache", ".svn", ".terraform", ".tmp.*", ".tox", ".venv", ".vs", ".webpack", ".yarn",
    "*[-_.@]cache", "*[-_.@]indexed", "*[-_.@]temp", "$recycle.bin", "adobe/common/ptx", "adobe/typeQuest",
    "aggregatedCache", "artifacts", "autofillStates", "backstageInAppNavCache", "blob_storage", "bower_components",
    "build", "cache", "cache[-_.@]*", "cache[0-9]*", "cacheStorage", "code cache", "code_tracker", "composer/files",
    "coreSync/cloudNative", "coreSync/plugins", "coverage-reports", "coverage", "crlCache", "cvs", "D3DSCache",
    "data/emojis", "dawnCache", "dawnGraphiteCache", "dawnWebGPUCache", "debugbar", "dim-1/mw$default", "dim1/mw$default",
    "dist-newstyle", "dist", "docs/_build", "gpuCache", "graphicsCache", "graphiteDawnCache", "grShaderCache", "htmlCache",
    "htmlCov", "hyphen-data", "identityCache", "indexed[-_.@]*", "indexedDB", "indexes", "jspm_packages", "junit",
    "legacy_web_files/ul_dir", "legacy_web_files/result", "lib/encodings", "local storage", "locales", "log", "logs",
    "media cache files", "meta/assets/indexes", "meta/assets/objects", "metadataIndexer", "node_modules", "node", "npm",
    "nvm", "obj", "office/*/aggMru", "office/*/dts", "office/*/usageMetricsStore", "office/*/wef", "officeFileCache",
    "packages", "patch64", "pnpm/store/links", "program64", "pythonLocator", "recent/automaticDestinations",
    "recent/customDestinations", "reports", "rsa", "scriptCache", "session storage", "shaderCache", "slCache",
    "spotify/data", "spotify/users", "steamLink/avatars", "storage/framework", "tapCache", "target", "temp", "temp[-_.@]*",
    "test-results", "tmp", "user/history", "user/webStorage", "uxp/plugins/external", "vendor", "venv", "virtualBkgnd_*",
    "vscode.git/askPass", "webCache2", "wheels", "x64", "x86", "xcuserdata"
})
"""Standard cache, build, dependency, and temporary directories to auto-ignore."""
# fmt: on

EXACT_IGNORE_NAMES: frozenset[str] = frozenset({
    path.lower() for path in AUTO_IGNORE_FOLDERS if "*" not in path and "[" not in path and "/" not in path
})
"""Pre-computed set of exact folder names to skip in `O(1)` time."""

WILDCARD_IGNORE_NAMES: list[re.Pattern[str]] = [
    re.compile(fnmatch.translate(path.lower()))
    for path in AUTO_IGNORE_FOLDERS
    if ("*" in path or "[" in path) and "/" not in path
]
"""Pre-compiled regex patterns for wildcard folder ignores without path separators."""

PATH_IGNORE_PARTS: tuple[str, ...] = tuple(
    path.lower() for path in AUTO_IGNORE_FOLDERS if "/" in path and "*" not in path and "[" not in path
)
"""Pre-computed tuple of multi-part directory paths to auto-ignore."""

_SEP: str = r"[-_~x@\s]+"
"""Regex pattern for word separators in generated filenames."""
_EXT: str = r"(?:\.[-_a-zA-Z0-9]+)*?$"
"""Regex pattern for optional trailing file extensions."""
_PRE: str = rf"^(?![a-zA-Z]+\.[a-zA-Z])(?:[a-zA-Z0-9]+{_SEP})*?"
"""Regex prefix pattern for delimited filename prefixes."""
_DATE: str = r"[12][0-9]{3}(?:0[1-9]|1[0-2])(?:0[1-9]|[12][0-9]|3[01])"
"""Regex pattern for matching ISO/compact date strings."""

# ruff:ignore[line-too-long]
_REOCCURRING: dict[str, str] = {
    "delimited_number": r"[-_][0-9]{1,2}",
    "num5-rand12": r"[0-9]{5}-[a-zA-Z0-9]{12}",
    "min_hex32": r"\.min_[a-fA-F0-9]{32}",
    "lower32_num1,2.hex64": r"[a-z]{32}_[0-9]{1,2}\.[a-fA-F0-9]{64}",
    "id3hex4": rf"\w{{3}}[a-fA-F0-9]{{4}}(?:{_SEP}|{_EXT})",
    "e_rand32": rf"e_[a-zA-Z0-9]{{32}}(?:{_SEP}|{_EXT})",
    "date": _DATE,
    "version.date": r"(?:[0-9]\.){3}" + _DATE,
    "delimited_date": r"(?:[0-9]{2}|[0-9]{4})[-.](?:[0-9]{2}|[0-9]{4})[-.](?:[0-9]{2}|[0-9]{4})",
    "base64": r"[+/0-9A-Za-z]{8,}={1,2}",
    "hex": r"(?:[a-fA-F0-9]{7,8}|[a-fA-F0-9]{16}[a-fA-F0-9]{20}|[a-fA-F0-9]{32}|[a-fA-F0-9]{38}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})",
    "uuid": rf"\{{?[a-zA-Z0-9]{{8}}-[a-zA-Z0-9]{{4}}-[a-zA-Z0-9]{{4}}-[a-zA-Z0-9]{{4}}-[a-zA-Z0-9]{{12}}\}}?(?:[-_a-zA-Z0-9]+(?:{_SEP}|{_EXT}))?",
    "sid": r"S-[0-9]+-[0-9]+(?:-[0-9]+){2,}",
    "domain": r"[-a-z]+(?:\.[-a-z]+){2,}",
}
"""Reoccurring sub-patterns found in generated hash or cache file/folder names."""

_STANDALONES: dict[str, str] = {
    "hex2": r"(?:[0-9][a-fA-F0-9]|[a-fA-F0-9][0-9])",
    "alt-lower2": r"alt-[a-z]{2}" + _EXT,
    "rand_num": r"[A-Z0-9]{2,6}_[a-z][0-9]" + _EXT,
    "id_num": r"(?:[a-zA-Z0-9]{6}-){2}[a-zA-Z0-9]{6}\s(?:[0-9]{2}|[a-z][0-9]{2})",
    "domain_hex": rf"{_REOCCURRING['domain']}_{_REOCCURRING['hex']}",
    "camelCase_version-hex64": r"[a-z]+(?:[A-Z][a-z]+)*?_[0-9]{1,2}(?:\.[0-9]{1,2})+-[a-fA-F0-9]{64}",
}
"""Standalone exact patterns identifying hash or unique generated items."""

HASH_NAME_PATTERN: re.Pattern[str] = re.compile(
    rf"(?:^(?:{'|'.join(_STANDALONES.values())})$|{_PRE}(?:(?:{_SEP})?(?:{'|'.join(_REOCCURRING.values())}))+{_EXT})"
)
"""Compiled regular expression matching auto-generated hash, UUID, or cache names."""

HEX_SEGMENT_PATTERN: re.Pattern[str] = re.compile(r"^[a-fA-F0-9]{8,}$")
"""Compiled regular expression matching hexadecimal segments of 8 or more characters."""

UUID_PATTERN: re.Pattern[str] = re.compile(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}")
"""Compiled regular expression detecting UUID sequences anywhere in a string."""

SEP_SPLITTER_PATTERN: re.Pattern[str] = re.compile(r"[-_~@\s]+")
"""Compiled regular expression used to split filenames into delimited segments."""
