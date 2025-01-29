from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import datetime

class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _description = 'Purchase Request'

    name = fields.Char(string="Request Name", readonly=True, default='New')
    requested_by = fields.Many2one('res.users', string="Requested By", required=True,
                                   default=lambda self: self.env.user)
    vendor_id = fields.Many2one('res.partner', string="Vendor", required=True)
    start_date = fields.Date(string="Start Date", default=lambda self: datetime.date.today())
    end_date = fields.Date(string="End Date")
    rejection_reason = fields.Text(string="Rejection Reason", readonly=True,
                                   states={'reject': [('invisible', False)], 'rejected': [('readonly', False)]})
    order_line_ids = fields.One2many('purchase.request.line', 'request_id', string="Order Lines")
    total_price = fields.Float(string="Total Price", compute='_compute_total_price', store=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'To Be Approved'),
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
        ('cancel', 'Cancelled')
    ], string="Status", default='draft', tracking=True)

    @api.depends('order_line_ids.total')
    def _compute_total_price(self):
        for record in self:
            record.total_price = sum(line.total for line in record.order_line_ids)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.request') or 'New'
        return super(PurchaseRequest, self).create(vals)

    @api.constrains('vendor_id')
    def _check_vendor(self):
        for record in self:
            if not record.vendor_id:
                raise UserError(_("The requested user's partner is required to proceed with the creation."))
###
        # Action Methods
    def action_submit_for_approval(self):
            """Submit the request for approval."""
            for request in self:
                if request.status != 'draft':
                    raise UserError(_('Only requests in Draft state can be submitted for approval.'))
                self.status = 'to_approve'
            #  return self.action_return_view()

    def action_cancel(self):
            """Cancel the request."""
            for request in self:
                if request.status not in ['draft', 'to_approve']:
                    raise UserError(_('You can only cancel requests in Draft or To Be Approved state.'))
                self.status = 'cancel'
            #  return self.action_return_view()

    def action_reset_to_draft(self):
            """Reset the request back to Draft."""
            for request in self:
                if request.status != 'cancel':
                    raise UserError(_('Only cancelled requests can be reset to draft.'))
            self.status = 'draft'
            #  return self.action_return_view()

    def action_approve(self):
        for request in self:
            if request.status != 'to_approve':
                raise UserError(_('Only requests in "To Be Approved" state can be approved.'))

            # Notify Purchase Managers via email
            purchase_manager_group = self.env.ref('purchase.group_purchase_manager')  # Load the Purchase Manager group
            if purchase_manager_group:
                # Get all the partner IDs (recipients) associated with the group's users
                partner_ids = purchase_manager_group.users.mapped('partner_id')
                if partner_ids:
                    # Find the email template
                    email_template = self.env.ref('purchase_request.email_template_purchase_request_approved')
                    if email_template:
                        for partner in partner_ids:
                            # Send the email to each partner
                            email_template.sudo().with_context(email_to=partner.email).send_mail(request.id,
                                                                                                 force_send=True)

            # Update request state to 'approved'
            self.status = 'approve'
    def action_reject(self):
        """Reject the request."""
        for request in self:
            if request.status != 'to_approve':
                raise UserError(_('Only requests in "To Be Approved" state can be rejected.'))
        # Open a wizard for rejection reason
            return {
                'type': 'ir.actions.act_window',
                'name': 'Reject Purchase Request',
                'res_model': 'purchase.request.reject.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_rejection_reason': self.rejection_reason},  # Pass rejection context
        }
    def action_create_po(self):
        for request in self:
            if request.status != 'approve':
                raise UserError("This request must be in 'Approved' state to create a PO.")

            # check total
            confirmed_po_qty = {}
            confirmed_pos = self.env['purchase.order'].search([
                 ('origin', '=', request.name),# Retrieves all pos
                 ('state', '=', 'purchase') # filters only confirmed pos
            ])
            #loops through confirmed pos and collect the sum
            for po in confirmed_pos:
                for po_line in po.order_line:
                    confirmed_po_qty[po_line.product_id.id] = (
                            confirmed_po_qty.get(po_line.product_id.id, 0) + po_line.product_qty
                    )# get() to avoid key_error
            # create dict to link and pass the values
            purchase_order_vals = {
                'partner_id' : request.vendor_id.id, # take the sam ven in the pr
                'date_order' : request.start_date,
                'origin' : request.name, # liiiiiinnnnnnnk
                'order_line' : [],

            }

            for line in request.order_line_ids:
                pr_requested_qty = line.quantity  # Requested quantity from PR
                confirmed_qty = confirmed_po_qty.get(line.product_id.id, 0)  # Already confirmed PO quantity
                remaining_qty = pr_requested_qty - confirmed_qty  # Calculate remaining quantity
                new_po_qty = min(line.quantity, remaining_qty)  # Ensure we don’t exceed PR

                # Check if adding this PO exceeds the PR quantity
                if new_po_qty <= 0:
                    raise UserError(
                        _(f"Cannot exceed requested quantity for {line.product_id.name}. "
                      f"Requested: {pr_requested_qty}, Already confirmed: {confirmed_qty}, "
                      f"Remaining: {remaining_qty}, Trying to add: {line.quantity}.")
                    )

                purchase_order_vals['order_line'].append((0,0, {
                    'product_id': line.product_id.id,
                    'product_qty': line.quantity,
                    'price_unit': line.price,
                    'date_planned': request.end_date,
                }))

            purchase_order = self.env['purchase.order'].create(purchase_order_vals)

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'res_id': purchase_order.id,
                'view_mode': 'form',
                'target': 'current',
            }

    all_po_quantities_fulfilled = fields.Boolean(
        string="All PO Quantities Fulfilled",
        compute="_compute_all_po_quantities_fulfilled",
        store=False
    )

    @api.depends('order_line_ids.quantity')
    def _compute_all_po_quantities_fulfilled(self):
        """Check if all PR quantities have been fulfilled by confirmed POs"""
        for request in self:
            confirmed_po_qty = {}
            confirmed_pos = self.env['purchase.order'].search([
                ('origin', '=', request.name),
                ('state', '=', 'purchase')  # Only count confirmed POs
            ])

            for po in confirmed_pos:
                for po_line in po.order_line:
                    confirmed_po_qty[po_line.product_id.id] = (
                            confirmed_po_qty.get(po_line.product_id.id, 0) + po_line.product_qty
                    )

            # Check if all PR quantities have been fully used
            all_fulfilled = True
            for line in request.order_line_ids:
                requested_qty = line.quantity
                confirmed_qty = confirmed_po_qty.get(line.product_id.id, 0)

                if confirmed_qty < requested_qty:
                    all_fulfilled = False
                    break  # At least one product is not fully covered

            request.all_po_quantities_fulfilled = all_fulfilled


class PurchaseRequestLine(models.Model):
    _name = 'purchase.request.line'
    _description = 'Purchase Request Line'

    request_id = fields.Many2one('purchase.request', string="Purchase Request")
    product_id = fields.Many2one('product.product', string="Product", required=True)
    description = fields.Char(string="Description", related='product_id.name', readonly=True)
    quantity = fields.Float(string="Quantity", default=1.0, required=True)
    price = fields.Float(string="Price", default=1.0, required=True)
    cost_price = fields.Float(string="Cost Price", related='product_id.standard_price', readonly=True, store=True)
    total = fields.Float(string="Total", compute='_compute_total', store=True)

    @api.depends('quantity', 'price')
    def _compute_total(self):
        for record in self:
            record.total = record.quantity * record.price
