# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright 2013
#    Author: Guewen Baconnier - Camptocamp SA
#            Augustin Cisterne-Kaasv - Elico-corp
#            David Béal - Akretion
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

from openerp.addons.connector.event import (on_record_write,
                                            on_record_create,
                                            on_record_unlink
                                            )

import openerp.addons.magentoerpconnect.consumer as magentoerpconnect

from openerp.addons.connector.connector import Binder
from openerp.addons.magentoerpconnect.connector import get_environment
from openerp.addons.magentoerpconnect.unit.delete_synchronizer import (
    export_delete_record)


EXPORT_RECORD_PRIORITY = {
    'magento.product.category': 130,
    'magento.product.product': 140,
    'magento.attribute.set': 100,
    'magento.product.attribute': 110,
    'magento.attribute.option': 120,
    'magento.product.image': 150,
    }

@on_record_create(model_names=[
        'magento.product.category',
        'magento.product.product',
        'magento.product.attribute',
        'magento.attribute.set',
        'magento.attribute.option',
        'magento.product.image',
    ])
@on_record_write(model_names=[
        'magento.product.category',
        'magento.product.product',
#        'magento.product.attribute',
        'magento.attribute.option',
        'magento.product.image',
    ])
def delay_export(session, model_name, record_id, vals=None):
    priority = EXPORT_RECORD_PRIORITY.get(model_name, 100) 
    magentoerpconnect.delay_export(session, model_name,
                                   record_id, vals=vals,
                                   priority=100)

@on_record_write(model_names=[
        'product.product',
        'product.category',
        'product.image',
#        'attribute.attribute',
        'attribute.option',
    ])
def delay_export_all_bindings(session, model_name, record_id, vals=None):
    magentoerpconnect.delay_export_all_bindings(session, model_name,
                                                record_id, vals=vals)

@on_record_write(model_names=[
        'product.template',
    ])
def delay_export_all_product_bindings(session, model_name, record_id, vals=None):
    if session.context.get('connector_no_export'):
        return
    model = session.pool.get(model_name)
    record = model.browse(session.cr, session.uid,
                          record_id, context=session.context)
    if not vals:
        return True
    for variant in record.variant_ids:
        magentoerpconnect.delay_export_all_bindings(session, variant._name,
                                                variant.id, vals=vals)


@on_record_unlink(model_names=[
        'magento.product.category',
        'magento.product.product',
        'magento.product.attribute',
        'magento.attribute.set',
    ])
def delay_unlink(session, model_name, record_id):
    magentoerpconnect.delay_unlink(session, model_name, record_id)


@on_record_unlink(model_names=[
        'product.category',
        'product.product',
        'attribute.attribute',
        'attribute.set',
    ])
def delay_unlink_all_bindings(session, model_name, record_id):
    magentoerpconnect.delay_unlink_all_bindings(session, model_name, record_id)

# DELETE OPTION CONSUMER
# To delete option, magento need the attribute id and the option id

@on_record_unlink(model_names=['attribute.option'])
def delay_unlink_all_option_bindings(session, model_name, record_id):
    if session.context.get('connector_no_export'):
        return
    model = session.pool.get(model_name)
    record = model.browse(session.cr, session.uid,
                          record_id, context=session.context)
    for binding in record.magento_bind_ids:
        delay_option_unlink(session, binding._model._name,
                     binding.id)


@on_record_unlink(model_names=['magento.attribute.option'])
def delay_option_unlink(session, model_name, record_id):
    if session.context.get('connector_no_export'):
        return
    model = session.pool.get(model_name)
    record = model.browse(session.cr, session.uid,
                          record_id, context=session.context)

    option_env = get_environment(session, 'magento.attribute.option',
                          record.backend_id.id)
    option_binder = option_env.get_connector_unit(Binder)
    
    mag_option_id = option_binder.to_backend(record.id)
    if mag_option_id:
        attr_env = get_environment(session, 'magento.product.attribute',
                                   record.backend_id.id)
        attr_binder = attr_env.get_connector_unit(Binder)
        
        mag_attr_id = attr_binder.to_backend(
            record.openerp_id.attribute_id.id, wrap=True)
        
        export_delete_record.delay(
            session, model_name,
            record.backend_id.id, (mag_attr_id, mag_option_id))

# DELETE IMAGE CONSUMER
# To delete image, magento need the product_id and the image_id
# see http://www.magentocommerce.com/api/soap/catalog/...
# catalogProductAttributeMedia/catalog_product_attribute_media.remove.html

@on_record_unlink(model_names=['magento.product.image'])
def delay_magento_image_unlink(session, model_name, record_id):
    if session.context.get('connector_no_export'):
        return
    model = session.pool.get('magento.product.image')
    record = model.browse(session.cr, session.uid,
                          record_id, context=session.context)
    magento_keys = []
    env = get_environment(session, 'magento.product.image',
                          record.backend_id.id)
    binder = env.get_connector_unit(Binder)
    magento_keys.append(binder.to_backend(record_id))
    env = get_environment(session, 'magento.product.product',
                          record.backend_id.id)
    binder = env.get_connector_unit(Binder)
    magento_keys.append(binder.to_backend(record.openerp_id.product_id.id, wrap=True))
    if magento_keys:
        export_delete_record.delay(session, 'magento.product.image',
                                   record.backend_id.id, magento_keys)

@on_record_unlink(model_names=['product.image'])
def delay_product_image_unlink(session, model_name, record_id):
    model = session.pool.get(model_name)
    record = model.browse(session.cr, session.uid,
                          record_id, context=session.context)
    for binding in record.magento_bind_ids:
        delay_magento_image_unlink(session, binding._name, binding.id)
