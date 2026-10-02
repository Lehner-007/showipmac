import unittest
import tempfile
from pathlib import Path
from core import ROOT,Network
from presentation import connection_labels,selection_label,display_date,local_time

class PresentationTests(unittest.TestCase):
    def test_date_formats(self):
        self.assertEqual(display_date('2026-09-29'),'29.09.2026')
        self.assertEqual(display_date('2026-09-28 – 2026-09-29'),'28.09.2026 – 29.09.2026')
        self.assertEqual(display_date('2022-08-27 (ieee-data)'),'27.08.2022 (ieee-data)')
        self.assertEqual(local_time('2026-09-29T12:00:00+00:00','en')[:10],'29.09.2026')

    def test_connection_detection_no_interface_name_guess(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            root=Path(directory)
            for name in ('eth9','eth2','anything','enpFake'):
                (root/name).mkdir()
            for name in ('eth9','eth2'):
                (root/name/'device').mkdir();(root/name/'type').write_text('1')
            (root/'anything'/'wireless').mkdir()
            nets=[Network(name,('192.0.2.2/24',),'',False) for name in ('eth9','eth2','anything','enpFake')]
            nets.append(Network('bridge0',('192.0.2.2/24',),'',True))
            text=lambda key:{'lan':'LAN','wlan':'WLAN','virtual':'virtuell'}[key]
            labels=connection_labels(nets,text,root)
            self.assertEqual(labels,dict(eth9='LAN 2',eth2='LAN 1',anything='WLAN',enpFake='',bridge0='virtuell'))
            self.assertEqual(selection_label(nets[0],labels['eth9'],''),'192.0.2.0/24 — LAN 2 → eth9')
            self.assertEqual(selection_label(nets[3],'',''),'192.0.2.0/24 — enpFake')
            self.assertNotEqual(selection_label(nets[0],labels['eth9'],''),selection_label(nets[1],labels['eth2'],''))
