import json,unittest
from pathlib import Path
from languages import validate_pack
ROOT=Path(__file__).resolve().parents[1]
class HelpLogoTests(unittest.TestCase):
 def test_bundled_logo_preserved_but_remote_images_removed(self):
  pack=json.loads((ROOT/'github/sprachpakete/fr.json').read_text())
  pack['help_html']=pack['help_html'].replace('</h1>','</h1><img src="https://example.invalid/tracker.png" onload="bad()">')
  _,_,help_html=validate_pack(pack)
  self.assertIn('data:image/png;base64,',help_html)
  self.assertNotIn('example.invalid',help_html)
  self.assertNotIn('onload',help_html)
