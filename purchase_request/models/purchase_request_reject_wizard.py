from odoo import models, fields, api


class PurchaseRequestRejectWizard(models.TransientModel):
    _name = 'purchase.request.reject.wizard'
    _description = 'Purchase Request Reject Wizard'

    rejection_reason = fields.Text(string="Rejection Reason", required=True)

    def confirm_action(self):
        active_id = self.env.context.get('active_id')
        purchase_request = self.env['purchase.request'].browse(active_id)
        purchase_request.write({
            'rejection_reason': self.rejection_reason,
            'status': 'reject'
        })
