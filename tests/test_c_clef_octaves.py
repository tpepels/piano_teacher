import base64
from io import BytesIO
from xml.etree import ElementTree as ET
import cairosvg
from PIL import Image


def test_clef_octave_variants_have_authentic_numerals_on_the_correct_side():
    from piano_teacher.notation.assets.glyphs import native_glyphs
    atlas=native_glyphs()
    base=atlas['clef_c']['bounds']
    for suffix,above in [('8va',True),('15ma',True),('15mb',False)]:
        name='clef_c_'+suffix
        assert name in atlas,name
        item=atlas[name]
        assert item['source']=='verovio'
        assert item['components'][0]=='E05C'
        root=ET.fromstring(item['svg'])
        assert sum(1 for n in root.iter() if n.tag.endswith('path'))>=2
        box=item['bounds']
        png=cairosvg.svg2png(bytestring=item['svg'].encode(),output_width=400)
        alpha=Image.open(BytesIO(png)).getchannel('A')
        if above:
            boundary=int((base[1]-box[1])*alpha.height/box[3])
            assert boundary>0 and alpha.crop((0,0,alpha.width,boundary)).getbbox()
        else:
            boundary=int((base[1]+base[3]-box[1])*alpha.height/box[3])
            assert boundary<alpha.height and alpha.crop((0,boundary,alpha.width,alpha.height)).getbbox()
