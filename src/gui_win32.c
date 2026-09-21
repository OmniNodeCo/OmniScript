#include "omni.h"
#ifdef _WIN32
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>

static Interp *G_ip;
static Element *G_els;
static int G_nels,G_w,G_h;
static COLORREF G_bg;

static int text_scale(int size){ return size<7?1:size/7; }
static void draw_text(HDC dc,int x,int y,const char *s,COLORREF col,int size){
    int scale=text_scale(size),i,r,q;
    for(i=0;s[i];i++) for(r=0;r<7;r++) for(q=0;q<5;q++) if(font_pixel(s[i],q,r)){
        RECT cell; cell.left=x+(i*6+q)*scale; cell.top=y+r*scale; cell.right=cell.left+scale; cell.bottom=cell.top+scale;
        SetBkColor(dc,col); ExtTextOutA(dc,0,0,ETO_OPAQUE,&cell,"",0,NULL);
    }
}
static int label_width(const char *s,int size){ int w=0; for(;*s;s++) w+=6; return w*text_scale(size); }
static void paint(HDC dc){
    int i; RECT all; HBRUSH bgbrush;
    all.left=0; all.top=0; all.right=G_w; all.bottom=G_h;
    bgbrush=CreateSolidBrush(G_bg); FillRect(dc,&all,bgbrush); DeleteObject(bgbrush);
    for(i=0;i<G_nels;i++){
        Element *r=&G_els[i];
        switch(r->kind){
            case E_RECT: {
                RECT rc; HBRUSH b=CreateSolidBrush(RGB(r->color[0],r->color[1],r->color[2]));
                rc.left=r->x; rc.top=r->y; rc.right=r->x+(r->w>0?r->w:0); rc.bottom=r->y+(r->h>0?r->h:0);
                FillRect(dc,&rc,b); DeleteObject(b); break;
            }
            case E_CIRCLE: {
                HBRUSH b=CreateSolidBrush(RGB(r->color[0],r->color[1],r->color[2]));
                HGDIOBJ oldpen=SelectObject(dc,GetStockObject(NULL_PEN));
                HGDIOBJ oldbrush=SelectObject(dc,b);
                if(r->r>=0) Ellipse(dc,r->x-r->r,r->y-r->r,r->x+r->r+1,r->y+r->r+1);
                SelectObject(dc,oldpen); SelectObject(dc,oldbrush); DeleteObject(b); break;
            }
            case E_LINE: {
                HPEN pen=CreatePen(PS_SOLID,r->w>0?r->w:1,RGB(r->color[0],r->color[1],r->color[2]));
                HGDIOBJ old=SelectObject(dc,pen);
                MoveToEx(dc,r->x,r->y,NULL); LineTo(dc,r->x2,r->y2);
                SelectObject(dc,old); DeleteObject(pen); break;
            }
            case E_TEXT:
                draw_text(dc,r->x,r->y,r->text?r->text:"",RGB(r->color[0],r->color[1],r->color[2]),r->size);
                break;
            case E_BUTTON: {
                RECT rc; HBRUSH face=CreateSolidBrush(RGB(0x21,0x26,0x2d)); HBRUSH edge=CreateSolidBrush(RGB(0x8b,0x94,0x9e));
                int size=r->h-8; if(size>14) size=14; if(size<8) size=8;
                rc.left=r->x; rc.top=r->y; rc.right=r->x+(r->w>0?r->w:0); rc.bottom=r->y+(r->h>0?r->h:0);
                FillRect(dc,&rc,face); FrameRect(dc,&rc,edge); DeleteObject(face); DeleteObject(edge);
                int tx=r->x+(r->w-label_width(r->text?r->text:"",size))/2;
                int ty=r->y+(r->h-7*text_scale(size))/2;
                if(tx<r->x+4) tx=r->x+4; if(ty<r->y+2) ty=r->y+2;
                draw_text(dc,tx,ty,r->text?r->text:"",RGB(255,255,255),size);
                break;
            }
            default: break;
        }
    }
}
static LRESULT CALLBACK wndproc(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp){
    if(msg==WM_PAINT){ PAINTSTRUCT ps; HDC dc=BeginPaint(hwnd,&ps); paint(dc); EndPaint(hwnd,&ps); return 0; }
    if(msg==WM_LBUTTONDOWN){
        int x=LOWORD(lp),y=HIWORD(lp),i;
        for(i=0;i<G_nels;i++){
            Element *r=&G_els[i];
            if(r->kind==E_BUTTON && x>=r->x && y>=r->y && x<r->x+r->w && y<r->y+r->h){
                if(r->action){
                    char m[512]; snprintf(m,sizeof(m),"clicked '%s' -> %s",r->text?r->text:"button",r->action); say(G_ip,m);
                    char *full=malloc(strlen(r->action)+16); sprintf(full,"%s 2>&1",r->action);
                    FILE *pp=_popen(full,"r");
                    if(pp){ char buf[4096]; size_t n; while((n=fread(buf,1,sizeof(buf)-1,pp))>0){ buf[n]='\0'; say_text(G_ip,buf);} _pclose(pp); }
                    free(full);
                }
                break;
            }
        }
        return 0;
    }
    if(msg==WM_KEYDOWN && (wp==VK_ESCAPE||wp=='Q')){ DestroyWindow(hwnd); return 0; }
    if(msg==WM_DESTROY){ PostQuitMessage(0); return 0; }
    return DefWindowProcA(hwnd,msg,wp,lp);
}
int gui_available(void){ return 1; }
int gui_show(Interp *ip, Element *elems, int nelems, int w, int h, const char *title, const unsigned char bg[3]){
    WNDCLASSA cls; HWND hwnd; RECT rc; MSG msg;
    G_ip=ip; G_els=elems; G_nels=nelems; G_w=w; G_h=h; G_bg=RGB(bg[0],bg[1],bg[2]);
    memset(&cls,0,sizeof(cls)); cls.lpfnWndProc=wndproc; cls.hInstance=GetModuleHandleA(NULL); cls.lpszClassName="OmniScript"; cls.hCursor=LoadCursorA(NULL,IDC_ARROW);
    if(!RegisterClassA(&cls) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) return 0;
    rc.left=0; rc.top=0; rc.right=w; rc.bottom=h; AdjustWindowRect(&rc,WS_OVERLAPPEDWINDOW,FALSE);
    hwnd=CreateWindowExA(0,"OmniScript",title,WS_OVERLAPPEDWINDOW,CW_USEDEFAULT,CW_USEDEFAULT,rc.right-rc.left,rc.bottom-rc.top,NULL,NULL,cls.hInstance,NULL);
    if(!hwnd) return 0;
    ShowWindow(hwnd,SW_SHOW); UpdateWindow(hwnd);
    while(GetMessageA(&msg,NULL,0,0)>0){ TranslateMessage(&msg); DispatchMessageA(&msg); }
    return 1;
}
#else
int gui_available(void){ return 0; }
int gui_show(Interp *ip, Element *elems, int nelems, int w, int h, const char *title, const unsigned char bg[3]){
    (void)ip;(void)elems;(void)nelems;(void)w;(void)h;(void)title;(void)bg; return 0;
}
#endif
