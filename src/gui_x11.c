#include "omni.h"
#ifdef HAVE_X11
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>
#include <stdlib.h>
#include <string.h>

static int text_scale(int size){ return size<7?1:size/7; }
static unsigned long alloc_color(Display *d, Colormap cm, const unsigned char rgb[3]){
    XColor c; c.red=(unsigned short)(rgb[0]*257u); c.green=(unsigned short)(rgb[1]*257u); c.blue=(unsigned short)(rgb[2]*257u); c.flags=DoRed|DoGreen|DoBlue;
    if(XAllocColor(d,cm,&c)) return c.pixel;
    return BlackPixel(d,DefaultScreen(d));
}
static void draw_text(Display *d, Window win, GC gc, int x, int y, const char *s, unsigned long pix, int size){
    int scale=text_scale(size), i,r,q;
    XSetForeground(d,gc,pix);
    for(i=0;s[i];i++) for(r=0;r<7;r++) for(q=0;q<5;q++) if(font_pixel(s[i],q,r))
        XFillRectangle(d,win,gc,x+(i*6+q)*scale,y+r*scale,(unsigned)scale,(unsigned)scale);
}
static int label_width(const char *s, int size){ int w=0; for(;*s;s++) w+=6; return w*text_scale(size); }

static void paint(Display *d, Window win, GC gc, Colormap cm, Element *els, int nels, int w, int h, unsigned long bgpix){
    int i;
    XSetLineAttributes(d,gc,1,LineSolid,CapButt,JoinMiter);
    XSetForeground(d,gc,bgpix);
    XFillRectangle(d,win,gc,0,0,(unsigned)w,(unsigned)h);
    for(i=0;i<nels;i++){
        Element *r=&els[i];
        unsigned long pix;
        switch(r->kind){
            case E_RECT:
                pix=alloc_color(d,cm,r->color);
                XSetForeground(d,gc,pix);
                XFillRectangle(d,win,gc,r->x,r->y,(unsigned)(r->w>0?r->w:0),(unsigned)(r->h>0?r->h:0));
                XFreeColors(d,cm,&pix,1,0);
                break;
            case E_CIRCLE:
                pix=alloc_color(d,cm,r->color);
                XSetForeground(d,gc,pix);
                if(r->r>=0) XFillArc(d,win,gc,r->x-r->r,r->y-r->r,(unsigned)(2*r->r+1),(unsigned)(2*r->r+1),0,360*64);
                XFreeColors(d,cm,&pix,1,0);
                break;
            case E_LINE:
                pix=alloc_color(d,cm,r->color);
                XSetForeground(d,gc,pix);
                XSetLineAttributes(d,gc,(unsigned)(r->w>0?r->w:1),LineSolid,CapRound,JoinRound);
                XDrawLine(d,win,gc,r->x,r->y,r->x2,r->y2);
                XSetLineAttributes(d,gc,1,LineSolid,CapButt,JoinMiter);
                XFreeColors(d,cm,&pix,1,0);
                break;
            case E_TEXT:
                pix=alloc_color(d,cm,r->color);
                draw_text(d,win,gc,r->x,r->y,r->text?r->text:"",pix,r->size);
                XFreeColors(d,cm,&pix,1,0);
                break;
            case E_BUTTON: {
                unsigned char face[3]={0x21,0x26,0x2d}, edge[3]={0x8b,0x94,0x9e}, ink[3]={0xff,0xff,0xff};
                unsigned long facepix=alloc_color(d,cm,face);
                unsigned long edgepix=alloc_color(d,cm,edge);
                unsigned long inkpix=alloc_color(d,cm,ink);
                int size=r->h-8; if(size>14) size=14; if(size<8) size=8;
                XSetForeground(d,gc,facepix);
                XFillRectangle(d,win,gc,r->x,r->y,(unsigned)(r->w>0?r->w:0),(unsigned)(r->h>0?r->h:0));
                XSetForeground(d,gc,edgepix);
                XDrawRectangle(d,win,gc,r->x,r->y,(unsigned)(r->w>0?r->w-1:0),(unsigned)(r->h>0?r->h-1:0));
                int tx=r->x+(r->w-label_width(r->text?r->text:"",size))/2;
                int ty=r->y+(r->h-7*text_scale(size))/2;
                if(tx<r->x+4) tx=r->x+4;
                if(ty<r->y+2) ty=r->y+2;
                draw_text(d,win,gc,tx,ty,r->text?r->text:"",inkpix,size);
                XFreeColors(d,cm,&facepix,1,0);
                XFreeColors(d,cm,&edgepix,1,0);
                XFreeColors(d,cm,&inkpix,1,0);
                break;
            }
            default: break;
        }
    }
    XFlush(d);
}

int gui_available(void){
    Display *d=XOpenDisplay(NULL);
    if(!d) return 0;
    XCloseDisplay(d);
    return 1;
}
int gui_show(Interp *ip, Element *elems, int nelems, int w, int h, const char *title, const unsigned char bg[3]){
    Display *d;
    Window win;
    GC gc;
    Colormap cm;
    Atom wm_delete;
    unsigned long bgpix;
    int screen,done=0;
    d=XOpenDisplay(NULL);
    if(!d) return 0;
    screen=DefaultScreen(d);
    cm=DefaultColormap(d,screen);
    bgpix=alloc_color(d,cm,bg);
    win=XCreateSimpleWindow(d,RootWindow(d,screen),0,0,(unsigned)w,(unsigned)h,1,BlackPixel(d,screen),bgpix);
    XStoreName(d,win,title);
    XSelectInput(d,win,ExposureMask|KeyPressMask|ButtonPressMask|StructureNotifyMask);
    wm_delete=XInternAtom(d,"WM_DELETE_WINDOW",False);
    XSetWMProtocols(d,win,&wm_delete,1);
    gc=XCreateGC(d,win,0,NULL);
    XMapWindow(d,win);
    while(!done){
        XEvent ev;
        XNextEvent(d,&ev);
        if(ev.type==Expose && ev.xexpose.count==0){
            paint(d,win,gc,cm,elems,nelems,w,h,bgpix);
        } else if(ev.type==KeyPress){
            char buf[16]; KeySym key;
            XLookupString(&ev.xkey,buf,sizeof(buf),&key,NULL);
            if(key==XK_Escape||buf[0]=='q') done=1;
        } else if(ev.type==ButtonPress){
            int i,x=ev.xbutton.x,y=ev.xbutton.y;
            for(i=0;i<nelems;i++){
                Element *r=&elems[i];
                if(r->kind==E_BUTTON && x>=r->x && y>=r->y && x<r->x+r->w && y<r->y+r->h){
                    if(r->action){
                        char msg[512]; snprintf(msg,sizeof(msg),"clicked '%s' -> %s",r->text?r->text:"button",r->action); say(ip,msg);
                        // run command
                        char *full=malloc(strlen(r->action)+16);
                        sprintf(full,"%s 2>&1",r->action);
                        FILE *pp=popen(full,"r");
                        if(pp){
                            char buf[4096]; size_t n;
                            while((n=fread(buf,1,sizeof(buf)-1,pp))>0){ buf[n]='\0'; say_text(ip,buf); }
                            pclose(pp);
                        }
                        free(full);
                    }
                    break;
                }
            }
        } else if(ev.type==ClientMessage && (Atom)ev.xclient.data.l[0]==wm_delete){
            done=1;
        }
    }
    XFreeGC(d,gc);
    XDestroyWindow(d,win);
    XFreeColors(d,cm,&bgpix,1,0);
    XCloseDisplay(d);
    return 1;
}
#else
int gui_available(void){ return 0; }
int gui_show(Interp *ip, Element *elems, int nelems, int w, int h, const char *title, const unsigned char bg[3]){
    (void)ip;(void)elems;(void)nelems;(void)w;(void)h;(void)title;(void)bg; return 0;
}
#endif
