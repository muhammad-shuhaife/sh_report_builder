"""Procedural, transparent body textures. No report layout or margin changes."""
from functools import lru_cache
from io import BytesIO
import math
from PIL import Image, ImageDraw, ImageFont

BODY_DESIGNS = [('dots', 'Fine dot grid'), ('linen', 'Woven paper'),
                ('grid', 'Technical grid'), ('diagonal', 'Diagonal lines'),
                ('halo', 'Soft colour wash'), ('frame', 'Double-line frame'),
                ('contour', 'Flowing contours'), ('watermark', 'Company watermark'),
                ('corners', 'Corner fade'), ('security', 'Guilloche pattern')]
TILED = {'dots', 'linen', 'grid', 'diagonal'}


@lru_cache(maxsize=32)
def make_texture(key, color, opacity, text='', font_bytes=None):
    if key not in dict(BODY_DESIGNS):
        raise ValueError('Invalid in-page design')
    if not 0 <= opacity <= 100:
        raise ValueError('Opacity must be between 0 and 100')
    size = (192, 192) if key in TILED else (700, 990)
    mask = Image.new('L', size)
    draw = ImageDraw.Draw(mask)
    w, h = size
    if key == 'dots':
        for x in range(8, w, 24):
            for y in range(8, h, 24): draw.ellipse((x, y, x+2, y+2), fill=255)
    elif key == 'linen':
        for y in range(0, h, 6): draw.line((0,y,w,y), fill=110)
        for x in range(0, w, 8): draw.line((x,0,x,h), fill=150)
    elif key == 'grid':
        for p in range(0, w, 32):
            draw.line((p,0,p,h),fill=255);draw.line((0,p,w,p),fill=255)
    elif key == 'diagonal':
        for x in range(-h,w,32):draw.line((x,0,x+h,h),fill=210,width=1)
    elif key in ('halo','corners'):
        # Raster gradients are reliable in both HTML and wkhtmltopdf.
        pixels=mask.load()
        for y in range(h):
            for x in range(w):
                a=max(0,1-math.hypot(x/w,y/h)/.65)
                b=max(0,1-math.hypot((w-x)/w,(h-y)/h)/.65)
                pixels[x,y]=int(255*max(a,b)*(1 if key=='halo' else .7))
    elif key=='frame':
        for inset in (5,15):draw.rectangle((inset,inset,w-inset-1,h-inset-1),outline=255,width=2)
    elif key=='contour':
        for i in range(25):draw.arc((w-80-i*37,h-160-i*41,w+240+i*37,h+280+i*41),160,340,fill=220,width=2)
    elif key=='security':
        for center in [(w*.25,h*.4),(w*.75,h*.65)]:
            for i in range(1,28):
                rx=i*26;ry=i*19;draw.ellipse((center[0]-rx,center[1]-ry,center[0]+rx,center[1]+ry),outline=150,width=1)
    elif key=='watermark':
        label=(text or 'YOUR COMPANY')[:80]
        font=ImageFont.truetype(BytesIO(font_bytes),64) if font_bytes else ImageFont.load_default()
        box=draw.textbbox((0,0),label,font=font)
        tile=Image.new('L',(max(1,box[2]-box[0]+30),max(1,box[3]-box[1]+30)))
        ImageDraw.Draw(tile).text((15-box[0],15-box[1]),label,font=font,fill=255)
        # Fit before rotation so long names stay inside the body.
        if tile.width>w*.85:
            tile=tile.resize((int(w*.85),max(1,int(tile.height*w*.85/tile.width))))
        tile=tile.rotate(35,expand=True,resample=Image.Resampling.BICUBIC)
        mask.paste(tile,((w-tile.width)//2,(h-tile.height)//2))
    image=Image.new('RGBA',size,color)
    image.putalpha(mask.point(lambda v:round(v*opacity/100)))
    out=BytesIO();image.save(out,format='PNG')
    return out.getvalue()
