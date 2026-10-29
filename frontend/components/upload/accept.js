// File-picker filter for library files. Extensions alone are not enough on
// every system: iPhone/iPad Safari and some Android pickers grey out CSVs
// unless a MIME type matches, and Windows with Excel installed reports CSVs
// as application/vnd.ms-excel. List both so the files can always be picked.
export const LIBRARY_ACCEPT = [
  ".csv", ".json", ".txt", ".tsv",
  "text/csv", "text/comma-separated-values", "application/csv", "application/vnd.ms-excel",
  "text/plain", "text/tab-separated-values", "application/json",
].join(",");
