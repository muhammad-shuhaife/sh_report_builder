# Report Builder for Odoo 20

Technical module: `sh_report_builder`  
Author and maintainer: **Shuhaife Binhamza**  
License: LGPL-3

[Portfolio](https://shuhaife.pages.dev/) · [LinkedIn](https://www.linkedin.com/in/shuhaife-binhamza/)

Build custom QWeb reports in an Odoo form editor with an unsaved live PDF preview.

- 18 page layouts, 12 table styles and 10 body textures.
- Headings, text, field lists, line tables, totals, images, signatures and page breaks.
- Uploaded/designed headers and footers, with per-page or once-only display.
- Paper formats, margins, fonts, colours and background watermarks.
- Independent image opacity, saturation, size and alignment controls.
- Page numbers and field-based PDF download filenames.
- Publish/unpublish actions that control the target model's Print menu.
- Settings-administrator access. No external rendering service or activation key.

## Requirements

- Odoo 20; the `base` and `web` modules. Website is **not** required.
- A configured Odoo PDF engine. Patched wkhtmltopdf was used for validation of headers, footers and banner-repeat controls.
- Python ReportLab and Pillow in the Odoo environment.
- Business apps are optional. Only their installed models are offered as starter report types.
- Supports installations accepting custom Python addons, such as on-premise and Odoo.sh. Not standard Odoo Online.

## New installation

1. Copy the `sh_report_builder` folder into an addons directory.
2. Restart Odoo, update Apps List and install **Report Builder**.
3. Open **Report Builder → Report Studio** as a Settings administrator.
4. Create a report, select a business model and an accessible sample record, then review the PDF.
5. Publish it to the model's Print menu. Use Apply Changes after editing a published design.

## Important: this is a technical module rename

This public addon replaces the development module named `report_builder`.
It retains the existing `report.builder` ORM models; it is not a separate compatible application.
**Do not install both addons in the same database, or uninstall the old addon to migrate.**
Uninstalling can remove saved report designs. For an existing installation, back up the database and plan a technical-module/XML-ID migration on a staging copy before replacing the old addon. Optional migration notes are supplied in the separate documentation ZIP.
A normal new database can install this release directly.

## Apps Store materials

- `static/description/index.html`: store-oriented description with real Odoo screenshots.
- `static/description/icon.png`: transparent 128 × 128 module icon.
- `static/description/banner.png`: cover image listed in the manifest.
- Optional publishing, rename and linked-listing documents are supplied separately; they are not needed to run the addon.

The store description avoids external hyperlinks because the Odoo Apps vendor rules restrict them. Your portfolio is the manifest's author website; both profile links remain available above and in the separate linked HTML edition.

## Validation

The addon was installed in an isolated Odoo 20 database **without Website**. Report creation, starter blocks, header/footer setup, publishing, asset/action registration and the live PDF preview were exercised there. Listing screenshots use fictional records from that database.
The original development database was not migrated or modified.

## 20.0.1.0.2

Based on 20.0.1.0.0. Removed the installation hook and decorative diagonal-arrow
spans from the New report and Use this combination controls. Both buttons retain
their normal actions. Optional publishing documents are distributed separately.
