"""Offline PNG rendering using macOS CoreGraphics and CoreText through ctypes."""
import ctypes as C
from pathlib import Path

P=C.c_void_p; D=C.c_double; I=C.c_int; L=C.c_long
class Point(C.Structure): _fields_=[('x',D),('y',D)]
class Size(C.Structure): _fields_=[('width',D),('height',D)]
class Rect(C.Structure): _fields_=[('origin',Point),('size',Size)]

def draw(scene,target):
    cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cg=C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    ct=C.CDLL('/System/Library/Frameworks/CoreText.framework/CoreText')
    io=C.CDLL('/System/Library/Frameworks/ImageIO.framework/ImageIO')
    def bind(lib,name,ret,args):
        f=getattr(lib,name);f.restype=ret;f.argtypes=args;return f
    string=bind(cf,'CFStringCreateWithCString',P,[P,C.c_char_p,C.c_uint32])
    release=bind(cf,'CFRelease',None,[P])
    colorspace=bind(cg,'CGColorSpaceCreateDeviceRGB',P,[])()
    context=bind(cg,'CGBitmapContextCreate',P,[P,C.c_size_t,C.c_size_t,C.c_size_t,C.c_size_t,P,C.c_uint32])(None,scene['width'],scene['height'],8,scene['width']*4,colorspace,1)
    if not context: raise RuntimeError('Cannot create graphics context')
    fillcolor=bind(cg,'CGContextSetRGBFillColor',None,[P,D,D,D,D])
    fill=bind(cg,'CGContextFillRect',None,[P,Rect])
    color=bind(cg,'CGColorCreateGenericRGB',P,[D,D,D,D])
    font=bind(ct,'CTFontCreateWithName',P,[P,D,P])
    dictionary=bind(cf,'CFDictionaryCreate',P,[P,P,P,L,P,P])
    attributed=bind(cf,'CFAttributedStringCreate',P,[P,P,P])
    line=bind(ct,'CTLineCreateWithAttributedString',P,[P])
    position=bind(cg,'CGContextSetTextPosition',None,[P,D,D])
    linedraw=bind(ct,'CTLineDraw',None,[P,P])
    def rgb(hex):return tuple(int(hex[i:i+2],16)/255 for i in (0,2,4))
    fillcolor(context,*rgb(scene['background']),1)
    fill(context,Rect(Point(0,0),Size(scene['width'],scene['height'])))
    fontkey=P.in_dll(ct,'kCTFontAttributeName').value
    colorkey=P.in_dll(ct,'kCTForegroundColorAttributeName').value
    keycallbacks=C.addressof((C.c_char*1).in_dll(cf,'kCFTypeDictionaryKeyCallBacks'))
    valcallbacks=C.addressof((C.c_char*1).in_dll(cf,'kCFTypeDictionaryValueCallBacks'))
    for item in scene['items']:
        x,y=item['x'],item['y']
        if 'text' not in item:
            fillcolor(context,*rgb(item.get('color','2346d8')),1)
            fill(context,Rect(Point(x,scene['height']-y-item.get('height',100)),Size(item.get('width',1600),item.get('height',100))))
            continue
        size=item.get('size',32)
        name=string(None,b'Helvetica-Bold' if item.get('bold') else b'Helvetica',0x08000100)
        f=font(name,size,None); release(name)
        ink=color(*rgb(item.get('color','14161b')),1)
        keys=(P*2)(fontkey,colorkey);values=(P*2)(f,ink)
        attrs=dictionary(None,keys,values,2,keycallbacks,valcallbacks)
        for i,part in enumerate(item['text'].splitlines()):
            s=string(None,part.encode(),0x08000100)
            a=attributed(None,s,attrs); l=line(a)
            position(context,x,scene['height']-y-size-i*size*1.3);linedraw(l,context)
            release(l);release(a);release(s)
        release(attrs);release(f);release(ink)
    image=bind(cg,'CGBitmapContextCreateImage',P,[P])(context)
    path=str(Path(target).resolve()).encode()
    url=bind(cf,'CFURLCreateFromFileSystemRepresentation',P,[P,C.c_char_p,L,C.c_bool])(None,path,len(path),False)
    kind=string(None,b'public.png',0x08000100)
    dest=bind(io,'CGImageDestinationCreateWithURL',P,[P,P,C.c_size_t,P])(url,kind,1,None)
    bind(io,'CGImageDestinationAddImage',None,[P,P,P])(dest,image,None)
    if not bind(io,'CGImageDestinationFinalize',C.c_bool,[P])(dest):raise RuntimeError('PNG export failed')
    for value in (dest,kind,url,image,context,colorspace):release(value)
