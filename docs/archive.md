# Kojin Labs research archive

The public page is at `archive/`. Visitors can search, preview, and download files.
There is no visitor upload, edit, or delete endpoint. GitHub is the source of truth.

## Where files go

Add published material only under **`archive-content/`**. The page and its index
are generated from that folder. You do not edit the catalog JavaScript or HTML
to publish a record.

| Path | Purpose |
| --- | --- |
| `archive-content/00-project-overview/` | Scope, plans, and project documentation |
| `archive-content/01-stakeholders/` | Interview records and stakeholder research |
| `archive-content/02-materials/` | Chemistry, materials, and literature notes |
| `archive-content/03-experiments/` | Test procedures, datasets, and figures |
| `archive-content/04-presentations/` | Decks, posters, and progress presentations |
| `archive/index.html`, `archive/archive.css`, `archive/archive.js` | Archive interface |
| `archive/manifest.json` | Generated catalog. Do not hand-edit |
| `scripts/build_archive.py` | Metadata validation, hashes, and index generation |

Each section contains `_section.json`:

```json
{
  "title": "Experiments and data",
  "description": "Test procedures, measurements, spreadsheets, and figures.",
  "order": 3
}
```

Folder names define organization, while `title` defines the visible heading.
All sections appear in one continuous catalog. There is no folder drill-down.
To add a new area, create a new subfolder and its `_section.json`. A nested area
is also possible, provided it has its own section file. Treat a published section
file as permanent, just like the records within it.

## Add a record

1. Place a file in the appropriate section folder. Use descriptive, versioned
   filenames, such as `2027-02-12-breakthrough-v1.xlsx`.
2. Add a matching metadata sidecar by appending **`.meta.json` to the complete
   filename**. Example: `2027-02-12-breakthrough-v1.xlsx.meta.json`.
3. Commit both files on a branch and open a pull request. Check that the
   **Archive checks / validate** job passes.
4. Merge the pull request. The existing Pages workflow validates and regenerates
   the catalog before publishing. A failed check stops that deployment.

The following is a format example, not an actual experiment:

```json
{
  "id": "breakthrough-v1",
  "title": "Breakthrough test, first run",
  "created": "2027-02-12",
  "description": "Concentration measurements and analysis for the first test run.",
  "researchers": ["Derek", "Shohom"],
  "tags": ["formaldehyde", "breakthrough", "humidity"],
  "preview": "2027-02-12-breakthrough-v1.preview.pdf"
}
```

Required fields: `id`, `title`, `created`, `description`, and `researchers`.
The date is the creation date you record for the artifact, not a claim derived
from the filesystem. The UI displays that date and separately identifies the
publication commit. Researcher credits are supplied by contributors, not inferred
from the Git author. The list may be empty for administrative documentation.

Optional fields: `tags`, `preview`, `supersedes`, and `source_url`.
Use a globally unique lowercase ID with hyphens. A `preview` must name a PDF
in the same folder. It does not need another metadata sidecar unless you also
want it to appear as its own record.

For a JSON dataset, use `data.json` plus `data.json.meta.json`. The distinction
between a JSON asset and a metadata sidecar is the `.meta.json` suffix.
Do not use `_section.json` or a name ending in `.meta.json` as an original asset.

The catalog searches titles, descriptions, researcher names, tags, filenames,
and section titles. It does not extract and index PDF or Office document bodies.

## Supported previews

- PDF: native browser PDF viewer. Download remains available on browsers that
  do not support an embedded viewer.
- PNG, JPEG, GIF, WebP, SVG: image preview.
- TXT, Markdown, CSV, TSV, JSON: plain-text preview up to 250 KB. HTML in notes
  stays text rather than executing. CSV/TSV previews show the raw text.
- Excel, PowerPoint, Word, OpenDocument, ZIP: original download. Include a separate
  PDF export for an in-page preview. The public site does not send originals to
  Google or Microsoft document viewers.

Authors control the archive files. Publish only material cleared for public
release, including consent for any interview notes. This repository and the
archive are public; there is no private or embargoed-record setting.

## Revisions and immutability

After publication, add a new file and metadata instead of overwriting an entry:

```json
{
  "id": "breakthrough-v2",
  "title": "Breakthrough test, corrected analysis",
  "created": "2027-02-19",
  "description": "Corrects the calibration used in the first analysis.",
  "researchers": ["Derek", "Shohom"],
  "tags": ["formaldehyde", "correction"],
  "supersedes": "breakthrough-v1"
}
```

Both records remain visible, with links between versions. Each original and PDF
preview has a generated SHA-256 checksum. Published records link to a GitHub copy
at the exact publication commit rather than a moving branch URL.

The validator remembers the first archived file blobs in the main branch's
first-parent history. It rejects modifications, renames, and deletions of those
published paths, including changes from an earlier failed push. Intermediate
changes to newly added files on a PR branch are allowed before first publication.
Do not merge feature branches containing unrelated published-file changes.

**This is a read-only, append-only publishing workflow, not tamper-proof storage.**
A repository administrator can change the workflow, rewrite history, or delete
the repository. For stronger enforcement, configure a branch ruleset requiring
pull requests, the `Archive checks / validate` status check, and no force pushes
or branch deletion. Those account settings are not changed by this implementation.
For legally required retention or permanent scholarly records, use a dedicated
retention service or repository such as an institutional archive.

A mistaken overwrite can be fixed by restoring the exact original bytes and
adding a separately named corrected version. Never bypass validation just to
make a deployment pass.

## Google Drive

Drive can be the collaboration workspace while GitHub stores published snapshots.

Recommended starting workflow:

1. Collaborate in Google Docs, Sheets, or Slides.
2. Export a snapshot: PDF for reading, plus XLSX/PPTX/DOCX when useful.
3. Place exports under `archive-content/` with the metadata sidecar.
4. Optionally put the original HTTPS Drive link in `source_url`. It is a
   convenience link, not the immutable archived record. It keeps Drive's own
   sharing permissions and may ask visitors to sign in.
5. Publish later revisions as new archive entries.

Google supports PDF and Office exports for these Workspace file types:
https://developers.google.com/workspace/drive/api/guides/ref-export-formats

A future one-way importer can export approved files from a specific Drive folder
and open a GitHub pull request containing the snapshots and metadata. It should
never replace an existing archived filename. It needs a selected folder,
permission to read it, a mapping from metadata to researcher names, and protected
server-side credentials. No Drive connection or automatic sync is enabled here.
Never put a Drive token or service-account key in the public website.

The Drive `files.export` endpoint limits exported content to 10 MB. That is a
limit of that API endpoint, not necessarily a limit on manual exports:
https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export

## Local development

No new package dependencies are needed. From the repository root:

```sh
python3 scripts/build_archive.py
python3 -m http.server 8000
```

Open `http://localhost:8000/archive/`. Run the generator again after changing
content, then refresh. Opening `index.html` directly with `file://` will not load
its JSON catalog reliably. The deployed site automatically regenerates the index.

Checks:

```sh
python3 -m unittest discover -s tests -v
node --check archive/archive.js
```

Keep each asset under 100 MiB. GitHub Pages published sites are limited to 1 GB,
so this design is suitable for modest project collections, not large raw datasets:
https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
