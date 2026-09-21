#include "omni.h"
#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <sys/types.h>

#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#define popen _popen
#define pclose _pclose
#else
#include <dirent.h>
#include <unistd.h>
#include <fcntl.h>
#endif

#define DEFAULT_W 640
#define DEFAULT_H 400
#define DEFAULT_TITLE "OmniScript"
#define DEFAULT_BG "#0d1117"
#define FALLBACK_BMP "drawing.bmp"

void interp_init(Interp *ip, FILE *out, const char *cwd){
    memset(ip,0,sizeof(*ip));
    ip->out=out;
    snprintf(ip->cwd,sizeof(ip->cwd),"%s",cwd);
    ip->draw_w=DEFAULT_W;
    ip->draw_h=DEFAULT_H;
    snprintf(ip->draw_title,sizeof(ip->draw_title),"%s",DEFAULT_TITLE);
    unsigned char bg[3]={0x0d,0x11,0x17};
    memcpy(ip->draw_bg,bg,3);
    ip->draw_cap=16;
    ip->draw_elems=malloc(sizeof(Element)*ip->draw_cap);
    ip->draw_nelems=0;
}
void interp_free(Interp *ip){
    if(ip->draw_elems){
        for(int i=0;i<ip->draw_nelems;i++){
            free(ip->draw_elems[i].text);
            free(ip->draw_elems[i].action);
        }
        free(ip->draw_elems);
    }
    // free env bindings (malloced names)
    Binding *b=ip->globals.head, *next;
    while(b){ next=b->next; free(b->name); /* values are arena */ free(b); b=next; }
    b=ip->modules.head;
    while(b){ next=b->next; free(b->name); free(b); b=next; }
}

/* helpers for draw */
static void ensure_cap(Interp *ip){
    if(ip->draw_nelems>=ip->draw_cap){
        ip->draw_cap*=2;
        ip->draw_elems=realloc(ip->draw_elems,sizeof(Element)*ip->draw_cap);
    }
}
static Element *new_element(Interp *ip, ElemKind kind, int line){
    ensure_cap(ip);
    Element *el=&ip->draw_elems[ip->draw_nelems++];
    memset(el,0,sizeof(Element));
    el->kind=kind; el->line=line;
    el->color[0]=0x58; el->color[1]=0xa6; el->color[2]=0xff;
    el->bg[0]=ip->draw_bg[0]; el->bg[1]=ip->draw_bg[1]; el->bg[2]=ip->draw_bg[2];
    return el;
}
static Element *element_copy_new(Interp *ip, Element *src){
    // for returning as Value, allocate heap Element
    Element *e=malloc(sizeof(Element));
    memcpy(e,src,sizeof(Element));
    if(src->text) e->text=strdup(src->text);
    if(src->action) e->action=strdup(src->action);
    return e;
}

/* kw helpers */
static Value *kw_get(Kwarg *kws, int n, const char *key){
    for(int i=0;i<n;i++) if(strcasecmp(kws[i].key,key)==0) return kws[i].val;
    return NULL;
}
static Value *kw_get_any(Kwarg *kws, int n, const char *k1, const char *k2, const char *k3, const char *k4, const char *k5, const char *k6){
    Value *v=NULL;
    if(k1){ v=kw_get(kws,n,k1); if(v) return v; }
    if(k2){ v=kw_get(kws,n,k2); if(v) return v; }
    if(k3){ v=kw_get(kws,n,k3); if(v) return v; }
    if(k4){ v=kw_get(kws,n,k4); if(v) return v; }
    if(k5){ v=kw_get(kws,n,k5); if(v) return v; }
    if(k6){ v=kw_get(kws,n,k6); if(v) return v; }
    return NULL;
}
static int parse_int_arg(Value *v, int def){
    if(!v) return def;
    if(v->kind==V_NUM) return (int)v->num;
    if(v->kind==V_BOOL) return v->boolean?1:0;
    if(v->kind==V_STR){ char *e; long l=strtol(v->str,&e,10); if(e!=v->str) return (int)l; }
    return def;
}
static const char *parse_str_arg(Interp *ip, Value *v, const char *def){
    if(!v) return def;
    return val_to_string(ip,v);
}
static int parse_pair(Interp *ip, Value *v, int *a, int *b){
    if(!v) return 0;
    if(v->kind==V_TUPLE && v->nitems==2){ *a=parse_int_arg(v->items[0],0); *b=parse_int_arg(v->items[1],0); return 1; }
    if(v->kind==V_STR){
        // try "x,y" or "x x y" or "800x600"
        char tmp[128]; snprintf(tmp,sizeof(tmp),"%s",v->str);
        for(int i=0;tmp[i];i++){ if(tmp[i]=='x'||tmp[i]==','||tmp[i]==';') tmp[i]=' '; }
        int x,y; if(sscanf(tmp,"%d %d",&x,&y)==2){ *a=x; *b=y; return 1; }
    }
    return 0;
}

/* full path */
static void full_path(Interp *ip, const char *given, char *out, size_t cap){
    int abs=0; size_t n=0,i;
#ifdef _WIN32
    abs=(given[0]&&given[1]==':')||given[0]=='\\'||given[0]=='/';
#else
    abs=given[0]=='/';
#endif
    if(!abs){
        for(i=0;ip->cwd[i]&&n+1<cap;i++) out[n++]=ip->cwd[i];
        if(n+1<cap) out[n++]='/';
    }
    for(i=0;given[i]&&n+1<cap;i++) out[n++]=given[i];
    out[n]='\0';
}
static void make_parents(const char *path){
    char tmp[4096]; size_t i,n=strlen(path);
    if(n>=sizeof(tmp)) return;
    memcpy(tmp,path,n+1);
    for(i=1;i<n;i++){
        if(tmp[i]=='/'||tmp[i]=='\\'){
            char save=tmp[i]; tmp[i]='\0';
#ifdef _WIN32
            _mkdir(tmp);
#else
            mkdir(tmp,0755);
#endif
            tmp[i]=save;
        }
    }
}

/* forward eval */
Value *eval_expr(Interp *ip, Node *node);
static Value *eval_call(Interp *ip, Node *call_node, Value *func_val, Value **args, int nargs, Kwarg *kws, int nkwargs, int line);

/* eval helpers */
static Value *eval_tuple(Interp *ip, Node *node){
    Value **items=malloc(sizeof(Value*)*(size_t)(node->nargs+1));
    for(int i=0;i<node->nargs;i++) items[i]=eval_expr(ip,node->args[i]);
    return val_tuple(ip,items,node->nargs);
}

/* ---------- draw builtins ---------- */
static Value *draw_window_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    int w=ip->draw_w, h=ip->draw_h;
    const char *title=ip->draw_title;
    const char *bg_str=NULL;
    unsigned char bg[3]; memcpy(bg,ip->draw_bg,3);
    // positional: w,h,title,bg OR single string "800x600" OR tuple
    if(nargs==1){
        int pw,ph;
        if(parse_pair(ip,args[0],&pw,&ph)){ w=pw; h=ph; }
        else if(args[0]->kind==V_STR){
            // maybe "800x600" handled by parse_pair
            // else treat as title?
            const char *s=args[0]->str;
            if(strchr(s,'x')||strchr(s,',')){ /* already handled */ }
            else title=s;
        }
    } else if(nargs>=2){
        w=parse_int_arg(args[0],w);
        h=parse_int_arg(args[1],h);
        if(nargs>=3) title=parse_str_arg(ip,args[2],title);
        if(nargs>=4) bg_str=parse_str_arg(ip,args[3],NULL);
    }
    // kwargs
    Value *vw=kw_get_any(kws, nkwargs, "width", "w", NULL, NULL, NULL, NULL);
    Value *vh=kw_get_any(kws, nkwargs, "height", "h", NULL, NULL, NULL, NULL);
    if(vw) w=parse_int_arg(vw,w);
    if(vh) h=parse_int_arg(vh,h);
    Value *vt=kw_get_any(kws, nkwargs, "title", "name", NULL, NULL, NULL, NULL);
    if(vt) title=parse_str_arg(ip,vt,title);
    Value *vb=kw_get_any(kws, nkwargs, "background", "bg", "color", "colour", NULL, NULL);
    if(vb) bg_str=parse_str_arg(ip,vb,NULL);
    // also support size=(w,h) and pos? No for window
    Value *vs=kw_get(kws,nkwargs,"size");
    if(vs){ int pw,ph; if(parse_pair(ip,vs,&pw,&ph)){ w=pw; h=ph; } }
    if(bg_str){ unsigned char col[3]; if(parse_color(bg_str,col)) memcpy(bg,col,3); }
    if(w<1||h<1) fail_at(ip,line,0,"window size cannot be %dx%d",w,h);
    ip->draw_w=w; ip->draw_h=h;
    snprintf(ip->draw_title,sizeof(ip->draw_title),"%s",title);
    memcpy(ip->draw_bg,bg,3);
    // also create window element for returning?
    Element tmp; memset(&tmp,0,sizeof(tmp)); tmp.kind=E_WINDOW; tmp.w=w; tmp.h=h; tmp.text=strdup(title); memcpy(tmp.bg,bg,3); tmp.line=line;
    Element *heap=element_copy_new(ip,&tmp); free(tmp.text);
    char msg[256]; snprintf(msg,sizeof(msg),"window %dx%d \"%s\"",w,h,title); say(ip,msg);
    return val_element(ip,heap);
}
static Value *draw_rect_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    int x=0,y=0,w=0,h=0;
    unsigned char col[3]={0x58,0xa6,0xff};
    // positional
    if(nargs>=4){ x=parse_int_arg(args[0],x); y=parse_int_arg(args[1],y); w=parse_int_arg(args[2],w); h=parse_int_arg(args[3],h); if(nargs>=5){ const char *cs=parse_str_arg(ip,args[4],NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); } } }
    // kwargs
    Value *vx=kw_get(kws,nkwargs,"x"); if(vx) x=parse_int_arg(vx,x);
    Value *vy=kw_get(kws,nkwargs,"y"); if(vy) y=parse_int_arg(vy,y);
    Value *vw=kw_get_any(kws, nkwargs, "width", "w", NULL, NULL, NULL, NULL); if(vw) w=parse_int_arg(vw,w);
    Value *vh=kw_get_any(kws, nkwargs, "height", "h", NULL, NULL, NULL, NULL); if(vh) h=parse_int_arg(vh,h);
    Value *vc=kw_get_any(kws, nkwargs, "color", "colour", "bg", "fill", NULL, NULL); if(vc){ const char *cs=parse_str_arg(ip,vc,NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); } }
    Value *vpos=kw_get(kws,nkwargs,"pos"); if(vpos){ int px,py; if(parse_pair(ip,vpos,&px,&py)){ x=px; y=py; } }
    Value *vsize=kw_get(kws,nkwargs,"size"); if(vsize){ int pw,ph; if(parse_pair(ip,vsize,&pw,&ph)){ w=pw; h=ph; } }
    Element *el=new_element(ip,E_RECT,line);
    el->x=x; el->y=y; el->w=w; el->h=h; memcpy(el->color,col,3);
    Element *heap=element_copy_new(ip,el);
    return val_element(ip,heap);
}
static Value *draw_circle_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    int x=0,y=0,r=0; unsigned char col[3]={0x58,0xa6,0xff};
    if(nargs>=3){ x=parse_int_arg(args[0],x); y=parse_int_arg(args[1],y); r=parse_int_arg(args[2],r); if(nargs>=4){ const char *cs=parse_str_arg(ip,args[3],NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); } } }
    Value *vx=kw_get(kws,nkwargs,"x"); if(vx) x=parse_int_arg(vx,x);
    Value *vy=kw_get(kws,nkwargs,"y"); if(vy) y=parse_int_arg(vy,y);
    Value *vr=kw_get_any(kws, nkwargs, "radius", "r", NULL, NULL, NULL, NULL); if(vr) r=parse_int_arg(vr,r);
    Value *vc=kw_get_any(kws, nkwargs, "color", "colour", "bg", "fill", NULL, NULL); if(vc){ const char *cs=parse_str_arg(ip,vc,NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); } }
    Value *vpos=kw_get(kws,nkwargs,"pos"); if(vpos){ int px,py; if(parse_pair(ip,vpos,&px,&py)){ x=px; y=py; } }
    Element *el=new_element(ip,E_CIRCLE,line); el->x=x; el->y=y; el->r=r; memcpy(el->color,col,3);
    Element *heap=element_copy_new(ip,el);
    return val_element(ip,heap);
}
static Value *draw_line_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    int x1=0,y1=0,x2=0,y2=0,width=1; unsigned char col[3]={0x58,0xa6,0xff};
    if(nargs>=4){ x1=parse_int_arg(args[0],x1); y1=parse_int_arg(args[1],y1); x2=parse_int_arg(args[2],x2); y2=parse_int_arg(args[3],y2); if(nargs>=5){ const char *cs=parse_str_arg(ip,args[4],NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); else width=parse_int_arg(args[4],width); } if(nargs>=6) width=parse_int_arg(args[5],width); } }
    Value *vx1=kw_get_any(kws, nkwargs, "x1", "x", NULL, NULL, NULL, NULL); if(vx1) x1=parse_int_arg(vx1,x1);
    Value *vy1=kw_get_any(kws, nkwargs, "y1", "y", NULL, NULL, NULL, NULL); if(vy1) y1=parse_int_arg(vy1,y1);
    Value *vx2=kw_get(kws,nkwargs,"x2"); if(vx2) x2=parse_int_arg(vx2,x2);
    Value *vy2=kw_get(kws,nkwargs,"y2"); if(vy2) y2=parse_int_arg(vy2,y2);
    Value *vc=kw_get_any(kws, nkwargs, "color", "colour", NULL, NULL, NULL, NULL); if(vc){ const char *cs=parse_str_arg(ip,vc,NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); } }
    Value *vw=kw_get_any(kws, nkwargs, "width", "w", "thickness", NULL, NULL, NULL); if(vw) width=parse_int_arg(vw,width);
    Value *vfrom=kw_get(kws,nkwargs,"from"); if(vfrom){ int px,py; if(parse_pair(ip,vfrom,&px,&py)){ x1=px; y1=py; } }
    Value *vto=kw_get(kws,nkwargs,"to"); if(vto){ int px,py; if(parse_pair(ip,vto,&px,&py)){ x2=px; y2=py; } }
    Element *el=new_element(ip,E_LINE,line); el->x=x1; el->y=y1; el->x2=x2; el->y2=y2; el->w=width; memcpy(el->color,col,3);
    Element *heap=element_copy_new(ip,el);
    return val_element(ip,heap);
}
static Value *draw_text_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    int x=0,y=0,size=14; unsigned char col[3]={0x58,0xa6,0xff}; const char *msg="";
    if(nargs>=3){ x=parse_int_arg(args[0],x); y=parse_int_arg(args[1],y); msg=parse_str_arg(ip,args[2],msg); if(nargs>=4){ const char *cs=parse_str_arg(ip,args[3],NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); } if(nargs>=5) size=parse_int_arg(args[4],size); } }
    Value *vx=kw_get(kws,nkwargs,"x"); if(vx) x=parse_int_arg(vx,x);
    Value *vy=kw_get(kws,nkwargs,"y"); if(vy) y=parse_int_arg(vy,y);
    Value *vm=kw_get_any(kws, nkwargs, "message", "text", "msg", "string", "content", NULL); if(vm) msg=parse_str_arg(ip,vm,msg);
    Value *vc=kw_get_any(kws, nkwargs, "color", "colour", NULL, NULL, NULL, NULL); if(vc){ const char *cs=parse_str_arg(ip,vc,NULL); if(cs){ unsigned char c[3]; if(parse_color(cs,c)) memcpy(col,c,3); } }
    Value *vs=kw_get_any(kws, nkwargs, "size", "font_size", NULL, NULL, NULL, NULL); if(vs) size=parse_int_arg(vs,size);
    Value *vpos=kw_get(kws,nkwargs,"pos"); if(vpos){ int px,py; if(parse_pair(ip,vpos,&px,&py)){ x=px; y=py; } }
    Element *el=new_element(ip,E_TEXT,line); el->x=x; el->y=y; el->text=strdup(msg); el->size=size; memcpy(el->color,col,3);
    Element *heap=element_copy_new(ip,el);
    return val_element(ip,heap);
}
static Value *draw_button_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    int x=0,y=0,w=120,h=32; const char *label="button"; const char *action=NULL;
    if(nargs>=5){ x=parse_int_arg(args[0],x); y=parse_int_arg(args[1],y); w=parse_int_arg(args[2],w); h=parse_int_arg(args[3],h); label=parse_str_arg(ip,args[4],label); if(nargs>=6) action=parse_str_arg(ip,args[5],NULL); }
    else if(nargs>=1){ // maybe button("label")?
        if(nargs==1){ label=parse_str_arg(ip,args[0],label); }
    }
    Value *vx=kw_get(kws,nkwargs,"x"); if(vx) x=parse_int_arg(vx,x);
    Value *vy=kw_get(kws,nkwargs,"y"); if(vy) y=parse_int_arg(vy,y);
    Value *vw=kw_get_any(kws, nkwargs, "width", "w", NULL, NULL, NULL, NULL); if(vw) w=parse_int_arg(vw,w);
    Value *vh=kw_get_any(kws, nkwargs, "height", "h", NULL, NULL, NULL, NULL); if(vh) h=parse_int_arg(vh,h);
    Value *vl=kw_get_any(kws, nkwargs, "label", "text", "title", "caption", "name", NULL); if(vl) label=parse_str_arg(ip,vl,label);
    Value *va=kw_get_any(kws, nkwargs, "action", "command", "on_click", "do", NULL, NULL); if(va) action=parse_str_arg(ip,va,NULL);
    Value *vpos=kw_get(kws,nkwargs,"pos"); if(vpos){ int px,py; if(parse_pair(ip,vpos,&px,&py)){ x=px; y=py; } }
    Value *vsize=kw_get(kws,nkwargs,"size"); if(vsize){ int pw,ph; if(parse_pair(ip,vsize,&pw,&ph)){ w=pw; h=ph; } }
    Element *el=new_element(ip,E_BUTTON,line); el->x=x; el->y=y; el->w=w; el->h=h; el->text=strdup(label); if(action) el->action=strdup(action);
    Element *heap=element_copy_new(ip,el);
    char msg[256]; snprintf(msg,sizeof(msg),"added button '%s' at (%d,%d)",label,x,y); say(ip,msg);
    return val_element(ip,heap);
}
static Value *draw_save_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    const char *path="drawing.bmp";
    if(nargs>=1) path=parse_str_arg(ip,args[0],path);
    Value *vp=kw_get_any(kws, nkwargs, "path", "file", "filename", "to", "name", NULL); if(vp) path=parse_str_arg(ip,vp,path);
    // render now
    char full[4096]; full_path(ip,path,full,sizeof(full));
    make_parents(full);
    // paint
    Canvas *c=canvas_new(ip->draw_w,ip->draw_h,ip->draw_bg);
    if(!c) fail_at(ip,line,0,"out of memory");
    for(int i=0;i<ip->draw_nelems;i++){
        Element *el=&ip->draw_elems[i];
        switch(el->kind){
            case E_RECT: canvas_rect(c,el->x,el->y,el->w,el->h,el->color); break;
            case E_CIRCLE: canvas_circle(c,el->x,el->y,el->r,el->color); break;
            case E_LINE: canvas_line(c,el->x,el->y,el->x2,el->y2,el->color,el->w); break;
            case E_TEXT: canvas_text(c,el->x,el->y,el->text?el->text:"",el->color,el->size); break;
            case E_BUTTON: {
                unsigned char face[3]={0x21,0x26,0x2d}, edge[3]={0x8b,0x94,0x9e}, ink[3]={0xff,0xff,0xff};
                canvas_rect(c,el->x,el->y,el->w,el->h,face);
                canvas_outline(c,el->x,el->y,el->w,el->h,edge);
                int sz=el->h-8; if(sz>14) sz=14; if(sz<8) sz=8;
                int tw=canvas_text_width(el->text?el->text:"",sz);
                int tx=el->x+(el->w-tw)/2; int ty=el->y+(el->h-sz)/2;
                if(tx<el->x+4) tx=el->x+4;
                if(ty<el->y+2) ty=el->y+2;
                canvas_text(c,tx,ty,el->text?el->text:"",ink,sz);
                break;
            }
            default: break;
        }
    }
    if(img_write_bmp(full,c)!=0){ int e=errno; canvas_free(c); fail_at(ip,line,0,"could not write %s: %s",path,strerror(e)); }
    canvas_free(c);
    char msg[512]; snprintf(msg,sizeof(msg),"wrote %s (%dx%d)",path,ip->draw_w,ip->draw_h); say(ip,msg);
    return val_str(ip,full);
}
static Value *draw_clear_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)args;(void)nargs;(void)kws;(void)nkwargs;(void)self;(void)line;
    for(int i=0;i<ip->draw_nelems;i++){ free(ip->draw_elems[i].text); free(ip->draw_elems[i].action); }
    ip->draw_nelems=0;
    say(ip,"cleared drawing");
    return val_nil(ip);
}
static Canvas *paint_all(Interp *ip){
    Canvas *c=canvas_new(ip->draw_w,ip->draw_h,ip->draw_bg);
    if(!c) return NULL;
    for(int i=0;i<ip->draw_nelems;i++){
        Element *el=&ip->draw_elems[i];
        switch(el->kind){
            case E_RECT: canvas_rect(c,el->x,el->y,el->w,el->h,el->color); break;
            case E_CIRCLE: canvas_circle(c,el->x,el->y,el->r,el->color); break;
            case E_LINE: canvas_line(c,el->x,el->y,el->x2,el->y2,el->color,el->w); break;
            case E_TEXT: canvas_text(c,el->x,el->y,el->text?el->text:"",el->color,el->size); break;
            case E_BUTTON: {
                unsigned char face[3]={0x21,0x26,0x2d}, edge[3]={0x8b,0x94,0x9e}, ink[3]={0xff,0xff,0xff};
                canvas_rect(c,el->x,el->y,el->w,el->h,face);
                canvas_outline(c,el->x,el->y,el->w,el->h,edge);
                int sz=el->h-8; if(sz>14) sz=14; if(sz<8) sz=8;
                int tw=canvas_text_width(el->text?el->text:"",sz);
                int tx=el->x+(el->w-tw)/2; int ty=el->y+(el->h-sz)/2;
                if(tx<el->x+4) tx=el->x+4;
                if(ty<el->y+2) ty=el->y+2;
                canvas_text(c,tx,ty,el->text?el->text:"",ink,sz);
                break;
            }
            default: break;
        }
    }
    return c;
}
static Value *draw_show_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    // if args contain elements, render those instead of global? For simplicity, if args have elements, use them as override list
    Element *elems=ip->draw_elems;
    int nelems=ip->draw_nelems;
    Element *tmp_elems=NULL;
    int tmp_nelems=0;
    int use_tmp=0;
    // check if any arg is element
    for(int i=0;i<nargs;i++) if(args[i]->kind==V_ELEMENT) use_tmp=1;
    if(use_tmp){
        // collect all element args
        tmp_elems=malloc(sizeof(Element)*(nargs+ip->draw_nelems+4));
        tmp_nelems=0;
        // first, if there is window element in args, use its size
        int w=ip->draw_w,h=ip->draw_h;
        char title[256]; snprintf(title,sizeof(title),"%s",ip->draw_title);
        unsigned char bg[3]; memcpy(bg,ip->draw_bg,3);
        int has_win=0;
        for(int i=0;i<nargs;i++){
            if(args[i]->kind==V_ELEMENT && args[i]->elem->kind==E_WINDOW){
                w=args[i]->elem->w; h=args[i]->elem->h;
                if(args[i]->elem->text) snprintf(title,sizeof(title),"%s",args[i]->elem->text);
                memcpy(bg,args[i]->elem->bg,3);
                has_win=1;
            }
        }
        if(!has_win){
            // add implicit window? no
        }
        // add all element args except window/save
        for(int i=0;i<nargs;i++){
            if(args[i]->kind==V_ELEMENT){
                if(args[i]->elem->kind==E_SAVE){
                    // handle save immediately? For now, save after render
                    continue;
                }
                if(args[i]->elem->kind==E_WINDOW) continue;
                tmp_elems[tmp_nelems++]=*args[i]->elem;
                // need to dup text/action to avoid free issues, but shallow copy okay for render
                if(args[i]->elem->text) tmp_elems[tmp_nelems-1].text=args[i]->elem->text;
                if(args[i]->elem->action) tmp_elems[tmp_nelems-1].action=args[i]->elem->action;
            }
        }
        // also include global elems if no window override? For compatibility, include global if not using only args? Let's include global elems as well if they exist and we are in old draw(window(), rect()) style where window is also in args, global may be empty.
        // If use_tmp and global empty, just use tmp. If global not empty, combine? Simpler: if use_tmp, use tmp only.
        elems=tmp_elems;
        nelems=tmp_nelems;
        // check for save kw
        Value *vsave=kw_get_any(kws, nkwargs, "path", "file", "save", NULL, NULL, NULL);
        const char *save_path=NULL;
        if(vsave) save_path=val_to_string(ip,vsave);
        // also check if any arg is save element
        for(int i=0;i<nargs;i++) if(args[i]->kind==V_ELEMENT && args[i]->elem->kind==E_SAVE) save_path=args[i]->elem->text;
        if(save_path){
            char full[4096]; full_path(ip,save_path,full,sizeof(full));
            make_parents(full);
            Canvas *c=canvas_new(w,h,bg);
            if(!c){ free(tmp_elems); fail_at(ip,line,0,"out of memory"); }
            for(int i=0;i<nelems;i++){
                Element *el=&elems[i];
                switch(el->kind){
                    case E_RECT: canvas_rect(c,el->x,el->y,el->w,el->h,el->color); break;
                    case E_CIRCLE: canvas_circle(c,el->x,el->y,el->r,el->color); break;
                    case E_LINE: canvas_line(c,el->x,el->y,el->x2,el->y2,el->color,el->w); break;
                    case E_TEXT: canvas_text(c,el->x,el->y,el->text?el->text:"",el->color,el->size); break;
                    case E_BUTTON: {
                        unsigned char face[3]={0x21,0x26,0x2d}, edge[3]={0x8b,0x94,0x9e}, ink[3]={0xff,0xff,0xff};
                        canvas_rect(c,el->x,el->y,el->w,el->h,face);
                        canvas_outline(c,el->x,el->y,el->w,el->h,edge);
                        int sz=el->h-8; if(sz>14) sz=14; if(sz<8) sz=8;
                        int tw=canvas_text_width(el->text?el->text:"",sz);
                        int tx=el->x+(el->w-tw)/2; int ty=el->y+(el->h-sz)/2;
                        if(tx<el->x+4) tx=el->x+4;
                        if(ty<el->y+2) ty=el->y+2;
                        canvas_text(c,tx,ty,el->text?el->text:"",ink,sz);
                        break;
                    }
                    default: break;
                }
            }
            if(img_write_bmp(full,c)!=0){ int e=errno; canvas_free(c); free(tmp_elems); fail_at(ip,line,0,"could not write %s: %s",save_path,strerror(e)); }
            canvas_free(c);
            char msg[512]; snprintf(msg,sizeof(msg),"wrote %s (%dx%d)",save_path,w,h); say(ip,msg);
            free(tmp_elems);
            return val_str(ip,full);
        }
        if(gui_available() && gui_show(ip,elems,nelems,w,h,title,bg)){
            free(tmp_elems);
            return val_nil(ip);
        }
        // fallback to file
        Canvas *c=canvas_new(w,h,bg);
        if(!c){ free(tmp_elems); fail_at(ip,line,0,"out of memory"); }
        for(int i=0;i<nelems;i++){
            Element *el=&elems[i];
            switch(el->kind){
                case E_RECT: canvas_rect(c,el->x,el->y,el->w,el->h,el->color); break;
                case E_CIRCLE: canvas_circle(c,el->x,el->y,el->r,el->color); break;
                case E_LINE: canvas_line(c,el->x,el->y,el->x2,el->y2,el->color,el->w); break;
                case E_TEXT: canvas_text(c,el->x,el->y,el->text?el->text:"",el->color,el->size); break;
                case E_BUTTON: {
                    unsigned char face[3]={0x21,0x26,0x2d}, edge[3]={0x8b,0x94,0x9e}, ink[3]={0xff,0xff,0xff};
                    canvas_rect(c,el->x,el->y,el->w,el->h,face);
                    canvas_outline(c,el->x,el->y,el->w,el->h,edge);
                    int sz=el->h-8; if(sz>14) sz=14; if(sz<8) sz=8;
                    int tw=canvas_text_width(el->text?el->text:"",sz);
                    int tx=el->x+(el->w-tw)/2; int ty=el->y+(el->h-sz)/2;
                    if(tx<el->x+4) tx=el->x+4;
                    if(ty<el->y+2) ty=el->y+2;
                    canvas_text(c,tx,ty,el->text?el->text:"",ink,sz);
                    break;
                }
                default: break;
            }
        }
        char full[4096]; full_path(ip,FALLBACK_BMP,full,sizeof(full));
        if(img_write_bmp(full,c)!=0){ int e=errno; canvas_free(c); free(tmp_elems); fail_at(ip,line,0,"could not write %s: %s",FALLBACK_BMP,strerror(e)); }
        canvas_free(c);
        char msg[512]; snprintf(msg,sizeof(msg),"no window, wrote %s (%dx%d)",FALLBACK_BMP,w,h); say(ip,msg);
        free(tmp_elems);
        return val_str(ip,full);
    }
    // no element args: render global
    Value *vsave=kw_get_any(kws, nkwargs, "path", "file", "save", NULL, NULL, NULL);
    if(vsave){
        return draw_save_fn(ip,args,nargs,kws,nkwargs,self,line);
    }
    if(ip->draw_nelems==0) fail_at(ip,line,0,"nothing to draw -- use draw.rect, draw.circle, etc. first");
    if(gui_available() && gui_show(ip,elems,nelems,ip->draw_w,ip->draw_h,ip->draw_title,ip->draw_bg)){
        return val_nil(ip);
    }
    Canvas *c=paint_all(ip);
    if(!c) fail_at(ip,line,0,"out of memory");
    char full[4096]; full_path(ip,FALLBACK_BMP,full,sizeof(full));
    if(img_write_bmp(full,c)!=0){ int e=errno; canvas_free(c); fail_at(ip,line,0,"could not write %s: %s",FALLBACK_BMP,strerror(e)); }
    canvas_free(c);
    char msg[512]; snprintf(msg,sizeof(msg),"no window, wrote %s (%dx%d)",FALLBACK_BMP,ip->draw_w,ip->draw_h); say(ip,msg);
    return val_str(ip,full);
}

/* ---------- cmd builtins ---------- */
static Value *cmd_run_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)kws;(void)nkwargs;(void)self;
    if(nargs<1) fail_at(ip,line,0,"cmd.run needs a command, like cmd.run(\"ls\")");
    const char *cmd=val_to_string(ip,args[0]);
    if(!cmd||!*cmd) fail_at(ip,line,0,"cmd.run got empty command");
    // simple popen 2>&1
    char *full=malloc(strlen(cmd)+16);
    sprintf(full,"%s 2>&1",cmd);
    FILE *pp=popen(full,"r");
    if(!pp){ free(full); fail_at(ip,line,0,"could not run '%s': %s",cmd,strerror(errno)); }
    char *buf=malloc(4096); size_t cap=4096,len=0;
    for(;;){
        if(len+1024>cap){ char *b=realloc(buf,cap*2); if(!b){ free(buf); pclose(pp); free(full); fail_at(ip,line,0,"out of memory"); } buf=b; cap*=2; }
        size_t n=fread(buf+len,1,1023,pp);
        len+=n;
        if(n<1023) break;
    }
    buf[len]='\0';
    int code=pclose(pp);
    free(full);
    if(len) say_text(ip,buf);
    free(buf);
#ifdef _WIN32
    // pclose returns exit code directly?
#else
    if(WIFEXITED(code)) code=WEXITSTATUS(code);
#endif
    if(code){ char msg[64]; snprintf(msg,sizeof(msg),"command exited %d",code); say(ip,msg); }
    return val_num(ip,code,1);
}
static Value *cmd_bg_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)kws;(void)nkwargs;(void)self;
    if(nargs<1) fail_at(ip,line,0,"cmd.bg needs a command");
    const char *cmd=val_to_string(ip,args[0]);
    if(!cmd||!*cmd) fail_at(ip,line,0,"cmd.bg got empty command");
#ifdef _WIN32
    char *cmdline=malloc(strlen(cmd)+16);
    sprintf(cmdline,"cmd.exe /c %s",cmd);
    STARTUPINFOA si; PROCESS_INFORMATION pi;
    memset(&si,0,sizeof(si)); si.cb=sizeof(si); memset(&pi,0,sizeof(pi));
    if(!CreateProcessA(NULL,cmdline,NULL,NULL,FALSE,DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP,NULL,NULL,&si,&pi)){
        free(cmdline); fail_at(ip,line,0,"could not start '%s'",cmd);
    }
    CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
    char msg[512]; snprintf(msg,sizeof(msg),"running in background: %s (pid %ld)",cmd,(long)pi.dwProcessId);
    say(ip,msg);
    free(cmdline);
    return val_num(ip,(double)pi.dwProcessId,1);
#else
    pid_t pid=fork();
    if(pid<0) fail_at(ip,line,0,"could not start '%s': %s",cmd,strerror(errno));
    if(pid==0){
        setsid();
        int devnull=open("/dev/null",O_RDWR);
        if(devnull>=0){ dup2(devnull,0); dup2(devnull,1); dup2(devnull,2); if(devnull>2) close(devnull); }
        execl("/bin/sh","sh","-c",cmd,(char*)NULL);
        _exit(127);
    }
    char msg[1024]; snprintf(msg,sizeof(msg),"running in background: %s (pid %ld)",cmd,(long)pid);
    say(ip,msg);
    return val_num(ip,(double)pid,1);
#endif
}
static Value *cmd_module_call(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    // cmd("ls") => run
    return cmd_run_fn(ip,args,nargs,kws,nkwargs,self,line);
}

/* ---------- pathlib builtins ---------- */
static Value *pathlib_read_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1){ Value *vp=kw_get(kws,nkwargs,"path"); if(vp) path=val_to_string(ip,vp); }
        else path=val_to_string(ip,args[0]);
    }
    if(!path) fail_at(ip,line,0,"pathlib.read needs a path");
    char full[4096]; full_path(ip,path,full,sizeof(full));
    FILE *f=fopen(full,"rb");
    if(!f) fail_at(ip,line,0,"%s is not there or cannot be read: %s",path,strerror(errno));
    size_t cap=4096,len=0; char *buf=malloc(cap);
    for(;;){
        if(len+1024>cap){ char *b=realloc(buf,cap*2); if(!b){ free(buf); fclose(f); fail_at(ip,line,0,"out of memory"); } buf=b; cap*=2; }
        size_t n=fread(buf+len,1,1023,f); len+=n; if(n<1023) break;
    }
    buf[len]='\0'; fclose(f);
    Value *v=val_str(ip,buf); free(buf); return v;
}
static Value *pathlib_write_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL; const char *content="";
    if(self && self->kind==V_PATH){ path=self->str; if(nargs>=1) content=val_to_string(ip,args[0]); else { Value *vc=kw_get_any(kws, nkwargs, "content", "data", "text", NULL, NULL, NULL); if(vc) content=val_to_string(ip,vc); } }
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.write needs path and content");
        path=val_to_string(ip,args[0]);
        if(nargs>=2) content=val_to_string(ip,args[1]);
        else { Value *vc=kw_get_any(kws, nkwargs, "content", "data", "text", NULL, NULL, NULL); if(vc) content=val_to_string(ip,vc); }
    }
    if(!path) fail_at(ip,line,0,"pathlib.write needs a path");
    char full[4096]; full_path(ip,path,full,sizeof(full));
    make_parents(full);
    FILE *f=fopen(full,"wb");
    if(!f) fail_at(ip,line,0,"could not write %s: %s",path,strerror(errno));
    fwrite(content,1,strlen(content),f); fclose(f);
    char msg[512]; snprintf(msg,sizeof(msg),"wrote %s (%lu bytes)",path,(unsigned long)strlen(content)); say(ip,msg);
    return val_str(ip,full);
}
static Value *pathlib_append_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL; const char *content="";
    if(self && self->kind==V_PATH){ path=self->str; if(nargs>=1) content=val_to_string(ip,args[0]); }
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.append needs path and content");
        path=val_to_string(ip,args[0]); if(nargs>=2) content=val_to_string(ip,args[1]);
    }
    (void)kws;(void)nkwargs;
    if(!path) fail_at(ip,line,0,"pathlib.append needs a path");
    char full[4096]; full_path(ip,path,full,sizeof(full));
    make_parents(full);
    FILE *f=fopen(full,"ab");
    if(!f) fail_at(ip,line,0,"could not append %s: %s",path,strerror(errno));
    fwrite(content,1,strlen(content),f); fclose(f);
    char msg[512]; snprintf(msg,sizeof(msg),"appended %s (%lu bytes)",path,(unsigned long)strlen(content)); say(ip,msg);
    return val_str(ip,full);
}
static Value *pathlib_exists_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1){ Value *vp=kw_get(kws,nkwargs,"path"); if(vp) path=val_to_string(ip,vp); else fail_at(ip,line,0,"pathlib.exists needs a path"); }
        else path=val_to_string(ip,args[0]);
    }
    char full[4096]; full_path(ip,path,full,sizeof(full));
    struct stat st; int ok=stat(full,&st)==0;
    return val_bool(ip,ok);
}
static Value *pathlib_is_file_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.is_file needs a path");
        path=val_to_string(ip,args[0]);
    }
    (void)kws;(void)nkwargs;
    char full[4096]; full_path(ip,path,full,sizeof(full));
    struct stat st; if(stat(full,&st)!=0) return val_bool(ip,0);
    return val_bool(ip,S_ISREG(st.st_mode));
}
static Value *pathlib_is_dir_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.is_dir needs a path");
        path=val_to_string(ip,args[0]);
    }
    (void)kws;(void)nkwargs;
    char full[4096]; full_path(ip,path,full,sizeof(full));
    struct stat st; if(stat(full,&st)!=0) return val_bool(ip,0);
    return val_bool(ip,S_ISDIR(st.st_mode));
}
static Value *pathlib_mkdir_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.mkdir needs a path");
        path=val_to_string(ip,args[0]);
    }
    (void)kws;(void)nkwargs;
    char full[4096]; full_path(ip,path,full,sizeof(full));
    // mkdir -p
    char tmp[4096]; size_t i,n=strlen(full);
    if(n>=sizeof(tmp)) fail_at(ip,line,0,"path too long");
    memcpy(tmp,full,n+1);
    for(i=1;i<n;i++){
        if(tmp[i]=='/'||tmp[i]=='\\'){
            char save=tmp[i]; tmp[i]='\0';
#ifdef _WIN32
            _mkdir(tmp);
#else
            mkdir(tmp,0755);
#endif
            tmp[i]=save;
        }
    }
#ifdef _WIN32
    int r=_mkdir(full);
#else
    int r=mkdir(full,0755);
#endif
    if(r!=0 && errno!=EEXIST) fail_at(ip,line,0,"could not mkdir %s: %s",path,strerror(errno));
    char msg[512]; snprintf(msg,sizeof(msg),"created dir %s",path); say(ip,msg);
    return val_bool(ip,1);
}
static Value *pathlib_delete_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.delete needs a path");
        path=val_to_string(ip,args[0]);
    }
    (void)kws;(void)nkwargs;
    char full[4096]; full_path(ip,path,full,sizeof(full));
    if(remove(full)!=0) fail_at(ip,line,0,"could not delete %s: %s",path,strerror(errno));
    char msg[512]; snprintf(msg,sizeof(msg),"deleted %s",path); say(ip,msg);
    return val_bool(ip,1);
}
static Value *pathlib_list_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=".";
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs>=1) path=val_to_string(ip,args[0]);
        else { Value *vp=kw_get(kws,nkwargs,"path"); if(vp) path=val_to_string(ip,vp); }
    }
    char full[4096]; full_path(ip,path,full,sizeof(full));
#ifdef _WIN32
    char pattern[4096]; snprintf(pattern,sizeof(pattern),"%s\\*",full);
    WIN32_FIND_DATAA fd; HANDLE h=FindFirstFileA(pattern,&fd);
    if(h==INVALID_HANDLE_VALUE) fail_at(ip,line,0,"could not list %s: %s",path,strerror(errno));
    Value **items=NULL; int cap=0,len=0;
    do{
        if(strcmp(fd.cFileName,".")==0||strcmp(fd.cFileName,"..")==0) continue;
        if(len==cap){
            cap=cap?cap*2:16;
            Value **ni=malloc(sizeof(Value*)*cap);
            for(int i=0;i<len;i++) ni[i]=items[i];
            free(items);
            items=ni;
        }
        items[len++]=val_str(ip,fd.cFileName);
    } while(FindNextFileA(h,&fd));
    FindClose(h);
    return val_tuple(ip,items,len);
#else
    DIR *d=opendir(full);
    if(!d) fail_at(ip,line,0,"could not list %s: %s",path,strerror(errno));
    Value **items=NULL; int cap=0,len=0;
    struct dirent *ent;
    while((ent=readdir(d))){
        if(strcmp(ent->d_name,".")==0||strcmp(ent->d_name,"..")==0) continue;
        if(len==cap){
            cap=cap?cap*2:16;
            Value **ni=malloc(sizeof(Value*)*cap);
            for(int i=0;i<len;i++) ni[i]=items[i];
            free(items);
            items=ni;
        }
        items[len++]=val_str(ip,ent->d_name);
    }
    closedir(d);
    return val_tuple(ip,items,len);
#endif
}
static Value *pathlib_join_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)kws;(void)nkwargs;(void)self;(void)line;
    if(nargs<1) fail_at(ip,line,0,"pathlib.join needs at least one path");
    char out[4096]; out[0]='\0'; size_t len=0;
    for(int i=0;i<nargs;i++){
        const char *p=val_to_string(ip,args[i]);
        if(!p) continue;
        if(len>0 && out[len-1]!='/' && out[len-1]!='\\'){
            if(len+1<sizeof(out)){ out[len++]='/'; out[len]='\0'; }
        }
        size_t pl=strlen(p);
        if(len+pl+1<sizeof(out)){ memcpy(out+len,p,pl); len+=pl; out[len]='\0'; }
    }
    return val_str(ip,out);
}
static Value *pathlib_name_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.name needs a path");
        path=val_to_string(ip,args[0]);
    }
    (void)kws;(void)nkwargs;
    const char *b=strrchr(path,'/'); const char *b2=strrchr(path,'\\');
    if(b2 && (!b||b2>b)) b=b2;
    const char *name=b?b+1:path;
    return val_str(ip,name);
}
static Value *pathlib_parent_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.parent needs a path");
        path=val_to_string(ip,args[0]);
    }
    (void)kws;(void)nkwargs;
    char tmp[4096]; snprintf(tmp,sizeof(tmp),"%s",path);
    char *b=strrchr(tmp,'/'); char *b2=strrchr(tmp,'\\');
    if(b2 && (!b||b2>b)) b=b2;
    if(b){ *b='\0'; if(tmp[0]=='\0') strcpy(tmp,"."); }
    else strcpy(tmp,".");
    return val_str(ip,tmp);
}
static Value *pathlib_ext_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    const char *path=NULL;
    if(self && self->kind==V_PATH) path=self->str;
    else {
        if(nargs<1) fail_at(ip,line,0,"pathlib.suffix needs a path");
        path=val_to_string(ip,args[0]);
    }
    (void)kws;(void)nkwargs;
    const char *b=strrchr(path,'/'); const char *b2=strrchr(path,'\\');
    if(b2 && (!b||b2>b)) b=b2;
    const char *name=b?b+1:path;
    const char *dot=strrchr(name,'.');
    if(!dot) return val_str(ip,"");
    return val_str(ip,dot);
}
static Value *pathlib_path_fn(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)kws;(void)nkwargs;(void)self;
    if(nargs<1) fail_at(ip,line,0,"Path needs a path");
    const char *p=val_to_string(ip,args[0]);
    return val_path(ip,p);
}

/* path methods table for bound */
static struct { const char *name; BuiltinFunc fn; } PATH_METHODS[] = {
    {"read", pathlib_read_fn},
    {"write", pathlib_write_fn},
    {"append", pathlib_append_fn},
    {"exists", pathlib_exists_fn},
    {"is_file", pathlib_is_file_fn},
    {"is_dir", pathlib_is_dir_fn},
    {"mkdir", pathlib_mkdir_fn},
    {"delete", pathlib_delete_fn},
    {"unlink", pathlib_delete_fn},
    {"remove", pathlib_delete_fn},
    {"list", pathlib_list_fn},
    {"listdir", pathlib_list_fn},
    {"join", pathlib_join_fn},
    {"name", pathlib_name_fn},
    {"basename", pathlib_name_fn},
    {"parent", pathlib_parent_fn},
    {"dirname", pathlib_parent_fn},
    {"suffix", pathlib_ext_fn},
    {"ext", pathlib_ext_fn},
    {NULL,NULL}
};

/* ---------- global builtins ---------- */
static Value *builtin_print(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)kws;(void)nkwargs;(void)self;(void)line;
    for(int i=0;i<nargs;i++){
        if(i) fputs(" ",ip->out);
        fputs(val_to_string(ip,args[i]),ip->out);
    }
    fputc('\n',ip->out); fflush(ip->out);
    return val_nil(ip);
}
static Value *builtin_input(Interp *ip, Value **args, int nargs, Kwarg *kws, int nkwargs, Value *self, int line){
    (void)self;
    const char *prompt="";
    if(nargs>=1) prompt=val_to_string(ip,args[0]);
    Value *vp=kw_get_any(kws, nkwargs, "prompt", "text", "msg", NULL, NULL, NULL); if(vp) prompt=val_to_string(ip,vp);
    if(prompt&&*prompt){ fwrite(prompt,1,strlen(prompt),ip->out); fflush(ip->out); }
    char *linebuf=malloc(4096);
    if(!fgets(linebuf,4096,stdin)){
        free(linebuf);
        fail_at(ip,line,0,"input() reached end");
    }
    size_t l=strlen(linebuf);
    while(l && (linebuf[l-1]=='\n'||linebuf[l-1]=='\r')) linebuf[--l]='\0';
    Value *v=val_str(ip,linebuf);
    free(linebuf);
    char msg[1024]; snprintf(msg,sizeof(msg),"typed: %s",val_to_string(ip,v)); say(ip,msg);
    return v;
}

/* ---------- modules init ---------- */
void modules_init(Interp *ip){
    // draw module
    Value *draw_mod=val_module(ip,"draw",draw_show_fn);
    env_set(&ip->modules,"draw",draw_mod);
    env_set(draw_mod->env,"window",val_func(ip,"window",draw_window_fn));
    env_set(draw_mod->env,"window_size",val_func(ip,"window_size",draw_window_fn));
    env_set(draw_mod->env,"rect",val_func(ip,"rect",draw_rect_fn));
    env_set(draw_mod->env,"circle",val_func(ip,"circle",draw_circle_fn));
    env_set(draw_mod->env,"line",val_func(ip,"line",draw_line_fn));
    env_set(draw_mod->env,"text",val_func(ip,"text",draw_text_fn));
    env_set(draw_mod->env,"button",val_func(ip,"button",draw_button_fn));
    env_set(draw_mod->env,"save",val_func(ip,"save",draw_save_fn));
    env_set(draw_mod->env,"show",val_func(ip,"show",draw_show_fn));
    env_set(draw_mod->env,"clear",val_func(ip,"clear",draw_clear_fn));
    // also allow draw() itself via mod_call, and draw.show etc already
    // cmd module
    Value *cmd_mod=val_module(ip,"cmd",cmd_module_call);
    env_set(&ip->modules,"cmd",cmd_mod);
    env_set(cmd_mod->env,"run",val_func(ip,"run",cmd_run_fn));
    env_set(cmd_mod->env,"bg",val_func(ip,"bg",cmd_bg_fn));
    env_set(cmd_mod->env,"background",val_func(ip,"background",cmd_bg_fn));
    // pathlib module
    Value *path_mod=val_module(ip,"pathlib",NULL);
    env_set(&ip->modules,"pathlib",path_mod);
    env_set(path_mod->env,"read",val_func(ip,"read",pathlib_read_fn));
    env_set(path_mod->env,"write",val_func(ip,"write",pathlib_write_fn));
    env_set(path_mod->env,"append",val_func(ip,"append",pathlib_append_fn));
    env_set(path_mod->env,"exists",val_func(ip,"exists",pathlib_exists_fn));
    env_set(path_mod->env,"is_file",val_func(ip,"is_file",pathlib_is_file_fn));
    env_set(path_mod->env,"is_dir",val_func(ip,"is_dir",pathlib_is_dir_fn));
    env_set(path_mod->env,"mkdir",val_func(ip,"mkdir",pathlib_mkdir_fn));
    env_set(path_mod->env,"delete",val_func(ip,"delete",pathlib_delete_fn));
    env_set(path_mod->env,"unlink",val_func(ip,"delete",pathlib_delete_fn));
    env_set(path_mod->env,"remove",val_func(ip,"delete",pathlib_delete_fn));
    env_set(path_mod->env,"list",val_func(ip,"list",pathlib_list_fn));
    env_set(path_mod->env,"listdir",val_func(ip,"list",pathlib_list_fn));
    env_set(path_mod->env,"join",val_func(ip,"join",pathlib_join_fn));
    env_set(path_mod->env,"basename",val_func(ip,"name",pathlib_name_fn));
    env_set(path_mod->env,"name",val_func(ip,"name",pathlib_name_fn));
    env_set(path_mod->env,"parent",val_func(ip,"parent",pathlib_parent_fn));
    env_set(path_mod->env,"dirname",val_func(ip,"parent",pathlib_parent_fn));
    env_set(path_mod->env,"suffix",val_func(ip,"suffix",pathlib_ext_fn));
    env_set(path_mod->env,"ext",val_func(ip,"suffix",pathlib_ext_fn));
    env_set(path_mod->env,"Path",val_func(ip,"Path",pathlib_path_fn));
    // global builtins
    env_set(&ip->globals,"print",val_func(ip,"print",builtin_print));
    env_set(&ip->globals,"input",val_func(ip,"input",builtin_input));
}

/* ---------- eval ---------- */
Value *eval_expr(Interp *ip, Node *node){
    if(!node) return val_nil(ip);
    switch(node->kind){
        case ND_NUM: return val_num(ip,node->num,node->is_int);
        case ND_STR: return val_str(ip,node->text);
        case ND_NAME: {
            Value *v=env_get(&ip->globals,node->text);
            if(v) return v;
            v=env_get(&ip->modules,node->text);
            if(v) return v;
            fail_at(ip,node->line,node->col,"name '%s' is not defined (did you import it?)",node->text);
            return val_nil(ip);
        }
        case ND_ATTR: {
            Value *obj=eval_expr(ip,node->child);
            if(obj->kind==V_MODULE){
                Value *v=env_get(obj->env,node->text);
                if(v) return v;
                fail_at(ip,node->line,node->col,"module '%s' has no '%s'",obj->mod_name,node->text);
            } else if(obj->kind==V_PATH){
                for(int i=0;PATH_METHODS[i].name;i++){
                    if(strcmp(PATH_METHODS[i].name,node->text)==0){
                        return val_func_bound(ip,node->text,PATH_METHODS[i].fn,obj);
                    }
                }
                fail_at(ip,node->line,node->col,"Path has no '%s'",node->text);
            } else if(obj->kind==V_STR){
                // allow string methods? No
                fail_at(ip,node->line,node->col,"'%s' has no attribute '%s'","str",node->text);
            } else {
                fail_at(ip,node->line,node->col,"value has no attribute '%s'",node->text);
            }
            return val_nil(ip);
        }
        case ND_TUPLE: {
            return eval_tuple(ip,node);
        }
        case ND_CALL: {
            Value *func=eval_expr(ip,node->child);
            Value **args=arena_alloc(ip->arena,sizeof(Value*)*(size_t)(node->nargs+1));
            for(int i=0;i<node->nargs;i++) args[i]=eval_expr(ip,node->args[i]);
            Kwarg *kws=arena_alloc(ip->arena,sizeof(Kwarg)*(size_t)(node->nkwargs+1));
            for(int i=0;i<node->nkwargs;i++){
                Node *kw=node->kwargs[i];
                kws[i].key=kw->text;
                kws[i].val=eval_expr(ip,kw->child);
                kws[i].line=kw->line; kws[i].col=kw->col;
            }
            return eval_call(ip,node,func,args,node->nargs,kws,node->nkwargs,node->line);
        }
        default:
            fail_at(ip,node->line,node->col,"cannot eval this");
            return val_nil(ip);
    }
}

static Value *eval_call(Interp *ip, Node *call_node, Value *func_val, Value **args, int nargs, Kwarg *kws, int nkwargs, int line){
    if(!func_val) fail_at(ip,line,0,"call of nothing");
    if(func_val->kind==V_FUNC){
        return func_val->func(ip,args,nargs,kws,nkwargs,func_val->bound,line);
    }
    if(func_val->kind==V_MODULE){
        if(func_val->mod_call) return func_val->mod_call(ip,args,nargs,kws,nkwargs,NULL,line);
        fail_at(ip,line,0,"module '%s' is not callable (try %s.show() or %s.run())",func_val->mod_name,func_val->mod_name,func_val->mod_name);
    }
    fail_at(ip,line,0,"this is not callable");
    return val_nil(ip);
}

/* statement eval */
static void eval_import(Interp *ip, Node *node){
    for(int i=0;i<node->nimports;i++){
        const char *modname=node->imports[i].name;
        const char *alias=node->imports[i].alias;
        // modname may have dots, take first part for lookup
        char base[256]; snprintf(base,sizeof(base),"%s",modname);
        char *dot=strchr(base,'.');
        if(dot) *dot='\0';
        Value *mod=env_get(&ip->modules,base);
        if(!mod){
            // try full name
            mod=env_get(&ip->modules,modname);
        }
        if(!mod) fail_at(ip,node->line,node->col,"no module named '%s' (available: draw, cmd, pathlib)",modname);
        // alias handling: if alias is first part? Use alias as given
        env_set(&ip->globals,alias,mod);
        char msg[256]; snprintf(msg,sizeof(msg),"imported %s as %s",modname,alias); say(ip,msg);
    }
}
static void eval_from_import(Interp *ip, Node *node){
    const char *base=node->from_base;
    char base_first[256]; snprintf(base_first,sizeof(base_first),"%s",base);
    char *dot=strchr(base_first,'.');
    if(dot) *dot='\0';
    Value *mod=env_get(&ip->modules,base_first);
    if(!mod) mod=env_get(&ip->modules,base);
    if(!mod) fail_at(ip,node->line,node->col,"no module named '%s'",base);
    if(node->nimports==1 && strcmp(node->imports[0].name,"*")==0){
        // import all
        Binding *b=mod->env->head;
        while(b){ env_set(&ip->globals,b->name,b->val); b=b->next; }
        char msg[256]; snprintf(msg,sizeof(msg),"imported * from %s",base); say(ip,msg);
        return;
    }
    for(int i=0;i<node->nimports;i++){
        const char *name=node->imports[i].name;
        const char *alias=node->imports[i].alias;
        Value *v=env_get(mod->env,name);
        if(!v) fail_at(ip,node->line,node->col,"module '%s' has no '%s'",base,name);
        env_set(&ip->globals,alias,v);
        char msg[256]; snprintf(msg,sizeof(msg),"imported %s.%s as %s",base,name,alias); say(ip,msg);
    }
}

int run_source(Interp *ip, const char *src, const char *name){
    Arena arena; char err[512]; int eline,ecol,nst,i;
    Token *toks; Node **sts;
    ip->source=(char*)src;
    if((unsigned char)ip->source[0]==0xef && (unsigned char)ip->source[1]==0xbb && (unsigned char)ip->source[2]==0xbf) ip->source+=3;
    ip->name=(char*)name;
    arena_init(&arena); ip->arena=&arena;
    if(setjmp(ip->jb)){
        char linebuf[512]; int j,col=ip->errcol>0?ip->errcol-1:0;
        fprintf(stderr,"%s:%d: %s\n",name,ip->errline,ip->errmsg);
        if(line_text(ip->source,ip->errline,linebuf,sizeof(linebuf))[0]){
            fprintf(stderr,"    %s\n    ",linebuf);
            for(j=0;j<col;j++) fputc(' ',stderr);
            fprintf(stderr,"^\n");
        }
        arena_free(&arena);
        ip->arena=NULL;
        return 1;
    }
    toks=tokenize(&arena,ip->source,err,&eline,&ecol);
    if(!toks) fail_at(ip,eline,ecol,"%s",err);
    sts=parse_program(&arena,toks,ip->source,name,&nst,err,&eline,&ecol);
    if(!sts) fail_at(ip,eline,ecol,"%s",err);
    for(i=0;i<nst;i++){
        Node *st=sts[i];
        if(st->kind==ND_IMPORT) eval_import(ip,st);
        else if(st->kind==ND_FROM_IMPORT) eval_from_import(ip,st);
        else if(st->kind==ND_ASSIGN){
            Value *v=eval_expr(ip,st->child);
            env_set(&ip->globals,st->text,v);
        } else if(st->kind==ND_EXPR_STMT){
            eval_expr(ip,st->child);
        }
    }
    arena_free(&arena);
    ip->arena=NULL;
    return 0;
}
