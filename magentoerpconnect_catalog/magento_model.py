# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright 2013
#    Author: Guewen Baconnier - Camptocamp
#            David Béal - Akretion
#            Sébastien Beau - Akretion
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging
from openerp.osv import orm, fields
from openerp.addons.connector.session import ConnectorSession
from openerp.addons.magentoerpconnect.unit.import_synchronizer import (
    import_batch,
    )
from openerp.addons.magentoerpconnect.unit.export_synchronizer import (
    MagentoExporter,
    )
from .consumer import delay_export


_logger = logging.getLogger(__name__)


class magento_backend(orm.Model):
    _inherit = 'magento.backend'

    def import_attribute_sets(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        self.check_magento_structure(cr, uid, ids, context=context)
        session = ConnectorSession(cr, uid, context=context)
        for backend_id in ids:
            import_batch.delay(session, 'magento.attribute.set', backend_id)
        return True

    _columns = {
        'attribute_set_tpl_id': fields.many2one(
            'magento.attribute.set',
            'Attribute set template',
            help="Attribute set ID basing on which the new attribute set "
            "will be created."),
        'auto_bind_image': fields.boolean(
            'Auto Bind Image',
            help=("Tic that box if you want to automatically export all the"
                  "image of a product without creating the binding manually")
            ),
        'auto_bind_product': fields.boolean(
            'Auto Bind Product',
            help=("Tic that box if you want to automatically export the"
                  "product when it's available for sell (sale_ok is tic)")
            ),
    }

    def _get_domain_to_export(self, cr, uid, ids, model, context=None):
        domain = [('sync_state', '=', 'todo')]
        if ids:
            domain.append(('backend_id', 'in', ids))
        return domain

    def _scheduler_export_catalog(self, cr, uid, ids=None, context=None):
        if ids and not hasattr(ids, '__iter__'):
            ids = [ids]
        models = [
            'magento.product.category',
            'magento.product.product',
            'magento.product.image',
            ]
        session = ConnectorSession(cr, uid, context=context)
        for model_name in models:
            _logger.info('Create Job for exporting model %s', model_name)
            obj = self.pool[model_name]
            domain = self._get_domain_to_export(
                cr, uid, ids, model_name, context=context)
            binding_ids = obj.search(cr, uid, domain, context=context)
            for binding_id in binding_ids:
                delay_export(session, model_name, binding_id,
                             vals={'sync_state': 'todo'})



# TODO if the way we process is valid this code should
# be move in connector-magento

class MagentoBindingCronExport(orm.AbstractModel):
    _name = 'magento.binding.cron.export'
    _cron_export = True

    #TODO maybe we should add a failed state?
    _columns = {
        'sync_state': fields.selection([
            ('done', 'Done'),
            ('todo', 'Todo'),
            ], string="Sync State"),
        'write_date': fields.datetime('Last Modif'),
    }

    _defaults = {
        'sync_state': 'done',
    }

    def _get_excluded_fields(self, cr, uid, context=None):
        return ['magento_id']

    def _should_be_exported(self, cr, uid, vals, context=None):
        excluded_fields = self._get_excluded_fields(cr, uid, context=context)
        fields = vals.keys()
        if fields and excluded_fields:
            fields = list(set(fields).difference(excluded_fields))
        res = (
            fields and
            (context is None or not context.get('connector_no_export')))
        if res:
            _logger.debug(
                'Magento Catalog Notify Export Set Export'
                'Fields was %s', vals.keys())
        else:
            _logger.debug(
                'Magento Catalog Notify Export Skip Export'
                'Fiels was %s', vals.keys())
        return res

    def create(self, cr, uid, vals, context=None):
        if self._should_be_exported(cr, uid, vals, context=context):
            vals['sync_state'] = 'todo'
        else:
            vals['sync_state'] = 'done'
        return super(MagentoBindingExport, self).create(
            cr, uid, vals, context=context)

    def write(self, cr, uid, ids, vals, context=None):
        if self._should_be_exported(cr, uid, vals, context=context):
            vals['sync_state'] = 'todo'
        return super(MagentoBindingCronExport, self).write(
            cr, uid, ids, vals, context=context)


def _after_export(self):
    if self.binding_record._columns.get('sync_state'):
        self.binding_record.write(
            {'sync_state': 'done'},
            context={'connector_no_export': True})

MagentoExporter._after_export = _after_export
