// Library file pickers have no `accept` filter on purpose. Android's picker
// greys out anything whose reported type isn't listed, and CSVs come through
// as text/csv, text/comma-separated-values, application/octet-stream and more
// depending on the app that saved them, so a visitor's Spotify CSV could not
// be picked at all. Any file can be chosen; we check the name afterwards and
// let a name with no extension through (some Android apps drop it), since the
// server reads the content anyway.
export const isLibraryFile = (f) => /\.(csv|json|txt|tsv)$/i.test(f.name || "") || !/\.[a-z0-9]{1,5}$/i.test(f.name || "");
export const NOT_LIBRARY_FILE = "That file isn't a library file. Pick a .csv, .json, .txt or .tsv export.";
