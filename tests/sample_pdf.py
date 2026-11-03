import math, pymupdf

def make_pdf(path):
    doc = pymupdf.open(); p = doc.new_page()
    r=p.rect
    p.draw_rect(r+(5,5,-5,-5), color=(0,0,0), width=0.5)          # bordo pagina spurio
    p.draw_line((300,10),(300,830), color=(0,0,0), width=0.3)     # linea verticale lunghissima
    # stella (contorno esterno) + doppione
    sh=p.new_shape()
    c=(200,300); pts=[]
    for i in range(10):
        a=math.pi/2+i*math.pi/5; R=120 if i%2==0 else 50
        pts.append(pymupdf.Point(c[0]+R*math.cos(a), c[1]-R*math.sin(a)))
    sh.draw_polyline(pts+[pts[0]]); sh.finish(color=(0,0,0), width=0.7, closePath=True); sh.commit()
    sh=p.new_shape(); sh.draw_polyline(pts+[pts[0]]); sh.finish(color=(0,0,0), width=0.7); sh.commit()
    # cerchio interno (finestra)
    p.draw_circle(c, 20, color=(0,0,0), width=0.7)
    # pieghe tratteggiate
    for i in range(0,10,2):
        p.draw_line(c, pts[i], color=(0,0,0), width=0.5, dashes="[4 3] 0")
    # contorno frammentato in 3 pezzi (rettangolo)
    p.draw_line((400,100),(500,100),color=(0,0,0)); p.draw_line((500,100),(500,200),color=(0,0,0))
    p.draw_polyline([(500,200),(400,200),(400,100)],color=(0,0,0))
    # riempimento colore + testo + immagine
    p.draw_rect(pymupdf.Rect(400,300,500,350), color=None, fill=(1,0.8,0.2))
    p.insert_text((350,500),"Piegare lungo le linee tratteggiate", fontsize=11)
    pix=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,20,20),0); pix.clear_with(200)
    p.insert_image(pymupdf.Rect(400,600,480,680), pixmap=pix)
    doc.save(path)
