# -*- coding: utf-8 -*-
"""
Unit tests for data model helpers
"""

from unittest import TestCase

from cplus_core.models.base import NcsPathway
from cplus_plugin.models.helpers import (
    clone_layer_component,
    create_ncs_pathway,
    ncs_pathway_to_dict,
)

from model_data_for_testing import get_valid_ncs_pathway, NCS_PATHWAY_DICT


class TestDataModelHelpers(TestCase):
    def setUp(self):
        self.ncs = get_valid_ncs_pathway()

    def test_ncs_pathway_to_dict(self):
        """Assert an NcsPathway object can be converted into
        the corresponding dictionary.
        """
        ncs_dict = ncs_pathway_to_dict(self.ncs, False)
        self.assertDictEqual(ncs_dict, NCS_PATHWAY_DICT)

    def test_create_ncs_pathway(self):
        """Compare two NcsPathway objects for equality."""
        ref_ncs = create_ncs_pathway(NCS_PATHWAY_DICT)
        self.assertTrue(ref_ncs == self.ncs)

    def test_clone_ncs_pathway(self):
        """Assert cloning of an NCS pathway object."""
        cloned_ncs = clone_layer_component(self.ncs, NcsPathway)
        self.assertIsNotNone(cloned_ncs)
        self.assertTrue(self.ncs.uuid == cloned_ncs.uuid)
        self.assertTrue(cloned_ncs.to_map_layer().isValid())
