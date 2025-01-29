{
    'name': 'Purchase Request',
    'version': '1.0',
    'category': 'Purchases',
    'summary': 'Custom Purchase Request Management',
    'description': 'Manages purchase requests with approval workflows.',
    'author': 'ibrahim fouad',
    'depends': ['base', 'purchase', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'views/purchase_request_views.xml',
        'views/purchase_request_reject_wizard.xml',
    ],
    'installable': True,
    'application': True,
}
