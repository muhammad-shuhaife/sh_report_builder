{'name': 'Report Builder',
 'summary': 'Visual PDF reports with live preview, design galleries, headers and watermarks',
 'description': 'Report Builder by Shuhaife Binhamza\n'
                '===================================\n'
                'Design and publish custom QWeb reports from an Odoo form editor.\n'
                '\n'
                '* 18 page designs, 12 table designs, and 10 in-page textures.\n'
                '* Unsaved live PDF preview using the configured Odoo PDF engine.\n'
                '* Uploaded or designed headers and footers with repeat controls.\n'
                '* Paper formats, fonts, report colours, page numbers, and download filenames.\n'
                '* Background watermarks with opacity, size, position, and saturation controls.\n'
                '* Starter reports for installed Sales, Accounting, Purchase, Inventory and '
                'Contacts models.\n'
                '* Settings-administrator access; no external rendering service or activation '
                'key.\n'
                '\n'
                'Requires Odoo 20, a working PDF engine, Pillow and ReportLab.\n'
                'The Website application is not required. Business applications are optional;\n'
                'only models installed in the database appear as report template choices.\n',
 'version': '20.0.1.0.2',
 'category': 'Productivity',
 'author': 'Shuhaife Binhamza',
 'depends': ['base', 'web'],
 'data': ['security/ir.access.csv',
          'views/sh_report_builder_views.xml',
          'views/report_studio_views.xml'],
 'assets': {'web.assets_backend': ['sh_report_builder/static/src/studio.js',
                                   'sh_report_builder/static/src/studio.xml',
                                   'sh_report_builder/static/src/studio.scss',
                                   'sh_report_builder/static/src/report_navigation.js',
                                   'sh_report_builder/static/src/report_navigation.xml',
                                   'sh_report_builder/static/src/range_field.js',
                                   'sh_report_builder/static/src/live_preview.js',
                                   'sh_report_builder/static/src/live_preview.xml',
                                   'sh_report_builder/static/src/live_preview.scss']},
 'external_dependencies': {'python': ['reportlab']},
 'application': True,
 'installable': True,
 'web_icon': 'sh_report_builder,static/description/icon.png',
 'license': 'LGPL-3',
 'maintainer': 'Shuhaife Binhamza',
 'website': 'https://shuhaife.pages.dev/',
 'images': ['static/description/banner.png']}
