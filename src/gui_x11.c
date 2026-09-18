/* Windows on Linux, through X11. */
#include "omni.h"

#ifdef HAVE_X11

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>
#include <stdlib.h>

/* Every element resolved to plain numbers before the window opens, so a bad
 * value fails before any X resource exists.
 */
typedef struct {
    ElemKind kind;
    int a, b, c, d, e;
    unsigned char col[3];
    const char *msg;
    Node *action;
} Resolved;

static int text_scale(int size) {
    return size < 7 ? 1 : size / 7;
}

static unsigned long alloc_color(Display *d, Colormap cm,
                                 const unsigned char rgb[3]) {
    XColor c;
    c.red = (unsigned short)(rgb[0] * 257u);
    c.green = (unsigned short)(rgb[1] * 257u);
    c.blue = (unsigned short)(rgb[2] * 257u);
    c.flags = DoRed | DoGreen | DoBlue;
    if (XAllocColor(d, cm, &c))
        return c.pixel;
    return BlackPixel(d, DefaultScreen(d));
}

static void resolve_all(Interp *ip, Element *elems, int nelems, Resolved *out) {
    int i;
    for (i = 0; i < nelems; i++) {
        Element *el = &elems[i];
        Resolved *r = &out[i];
        r->kind = el->kind;
        r->msg = NULL;
        r->action = NULL;
        switch (el->kind) {
        case E_RECT:
            r->a = elem_num(el->slot[0], 0, "rect's x", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "rect's y", el->line, ip);
            r->c = elem_num(el->slot[2], 0, "rect's width", el->line, ip);
            r->d = elem_num(el->slot[3], 0, "rect's height", el->line, ip);
            elem_rgb(el->slot[4], el->line, "#58a6ff", r->col, ip);
            break;
        case E_CIRCLE:
            r->a = elem_num(el->slot[0], 0, "circle's x", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "circle's y", el->line, ip);
            r->c = elem_num(el->slot[2], 0, "circle's radius", el->line, ip);
            elem_rgb(el->slot[3], el->line, "#58a6ff", r->col, ip);
            break;
        case E_LINE:
            r->a = elem_num(el->slot[0], 0, "line's x1", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "line's y1", el->line, ip);
            r->c = elem_num(el->slot[2], 0, "line's x2", el->line, ip);
            r->d = elem_num(el->slot[3], 0, "line's y2", el->line, ip);
            r->e = elem_num(el->slot[5], 1, "line's width", el->line, ip);
            elem_rgb(el->slot[4], el->line, "#58a6ff", r->col, ip);
            break;
        case E_TEXT:
            r->a = elem_num(el->slot[0], 0, "text's x", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "text's y", el->line, ip);
            r->c = elem_num(el->slot[4], 14, "text's size", el->line, ip);
            r->msg = elem_str(el->slot[2], "", ip);
            elem_rgb(el->slot[3], el->line, "#58a6ff", r->col, ip);
            break;
        case E_BUTTON:
            r->a = elem_num(el->slot[0], 0, "button's x", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "button's y", el->line, ip);
            r->c = elem_num(el->slot[2], 120, "button's width", el->line, ip);
            r->d = elem_num(el->slot[3], 32, "button's height", el->line, ip);
            r->msg = elem_str(el->slot[4], "button", ip);
            r->action = el->action;
            break;
        default:
            break;
        }
    }
}

static void draw_text(Display *d, Window win, GC gc, int x, int y,
                      const char *s, unsigned long pix, int size) {
    int scale = text_scale(size), i, r, q;
    XSetForeground(d, gc, pix);
    for (i = 0; s[i]; i++) {
        for (r = 0; r < 7; r++) {
            for (q = 0; q < 5; q++) {
                if (font_pixel(s[i], q, r))
                    XFillRectangle(d, win, gc, x + (i * 6 + q) * scale,
                                   y + r * scale, (unsigned)scale,
                                   (unsigned)scale);
            }
        }
    }
}

static int label_width(const char *s, int size) {
    int w = 0;
    for (; *s; s++)
        w += 6;
    return w * text_scale(size);
}

static void paint(Display *d, Window win, GC gc, Colormap cm, Resolved *els,
                  int nels, int w, int h, unsigned long bgpix) {
    int i;
    XSetLineAttributes(d, gc, 1, LineSolid, CapButt, JoinMiter);
    XSetForeground(d, gc, bgpix);
    XFillRectangle(d, win, gc, 0, 0, (unsigned)w, (unsigned)h);
    for (i = 0; i < nels; i++) {
        Resolved *r = &els[i];
        unsigned long pix;
        switch (r->kind) {
        case E_RECT:
            pix = alloc_color(d, cm, r->col);
            XSetForeground(d, gc, pix);
            XFillRectangle(d, win, gc, r->a, r->b, (unsigned)(r->c > 0 ? r->c : 0),
                           (unsigned)(r->d > 0 ? r->d : 0));
            XFreeColors(d, cm, &pix, 1, 0);
            break;
        case E_CIRCLE:
            pix = alloc_color(d, cm, r->col);
            XSetForeground(d, gc, pix);
            if (r->c >= 0)
                XFillArc(d, win, gc, r->a - r->c, r->b - r->c,
                         (unsigned)(2 * r->c + 1), (unsigned)(2 * r->c + 1),
                         0, 360 * 64);
            XFreeColors(d, cm, &pix, 1, 0);
            break;
        case E_LINE:
            pix = alloc_color(d, cm, r->col);
            XSetForeground(d, gc, pix);
            XSetLineAttributes(d, gc, (unsigned)(r->e > 0 ? r->e : 1), LineSolid,
                               CapRound, JoinRound);
            XDrawLine(d, win, gc, r->a, r->b, r->c, r->d);
            XSetLineAttributes(d, gc, 1, LineSolid, CapButt, JoinMiter);
            XFreeColors(d, cm, &pix, 1, 0);
            break;
        case E_TEXT:
            pix = alloc_color(d, cm, r->col);
            draw_text(d, win, gc, r->a, r->b, r->msg, pix, r->c);
            XFreeColors(d, cm, &pix, 1, 0);
            break;
        case E_BUTTON: {
            unsigned char face[3] = { 0x21, 0x26, 0x2d };
            unsigned char edge[3] = { 0x8b, 0x94, 0x9e };
            unsigned char ink[3] = { 0xff, 0xff, 0xff };
            unsigned long facepix = alloc_color(d, cm, face);
            unsigned long edgepix = alloc_color(d, cm, edge);
            unsigned long inkpix = alloc_color(d, cm, ink);
            int size = r->d - 8, tx, ty;
            if (size > 14)
                size = 14;
            if (size < 8)
                size = 8;
            XSetForeground(d, gc, facepix);
            XFillRectangle(d, win, gc, r->a, r->b,
                           (unsigned)(r->c > 0 ? r->c : 0),
                           (unsigned)(r->d > 0 ? r->d : 0));
            XSetForeground(d, gc, edgepix);
            XDrawRectangle(d, win, gc, r->a, r->b,
                           (unsigned)(r->c > 0 ? r->c - 1 : 0),
                           (unsigned)(r->d > 0 ? r->d - 1 : 0));
            tx = r->a + (r->c - label_width(r->msg, size)) / 2;
            ty = r->b + (r->d - 7 * text_scale(size)) / 2;
            if (tx < r->a + 4)
                tx = r->a + 4;
            if (ty < r->b + 2)
                ty = r->b + 2;
            draw_text(d, win, gc, tx, ty, r->msg, inkpix, size);
            XFreeColors(d, cm, &facepix, 1, 0);
            XFreeColors(d, cm, &edgepix, 1, 0);
            XFreeColors(d, cm, &inkpix, 1, 0);
            break;
        }
        default:
            break;
        }
    }
    XFlush(d);
}

int gui_available(void) {
    Display *d = XOpenDisplay(NULL);
    if (!d)
        return 0;
    XCloseDisplay(d);
    return 1;
}

int gui_show(Interp *ip, Element *elems, int nelems, int w, int h,
             const char *title, const unsigned char bg[3]) {
    Display *d;
    Window win;
    GC gc;
    Colormap cm;
    Resolved *rels;
    Atom wm_delete;
    unsigned long bgpix;
    int screen, done = 0;
    rels = malloc(sizeof(Resolved) * (size_t)(nelems + 1));
    if (!rels)
        return 0;
    resolve_all(ip, elems, nelems, rels);   /* may fail before X opens */
    d = XOpenDisplay(NULL);
    if (!d) {
        free(rels);
        return 0;
    }
    screen = DefaultScreen(d);
    cm = DefaultColormap(d, screen);
    bgpix = alloc_color(d, cm, bg);
    win = XCreateSimpleWindow(d, RootWindow(d, screen), 0, 0, (unsigned)w,
                              (unsigned)h, 1, BlackPixel(d, screen), bgpix);
    XStoreName(d, win, title);
    XSelectInput(d, win, ExposureMask | KeyPressMask | ButtonPressMask |
                 StructureNotifyMask);
    wm_delete = XInternAtom(d, "WM_DELETE_WINDOW", False);
    XSetWMProtocols(d, win, &wm_delete, 1);
    gc = XCreateGC(d, win, 0, NULL);
    XMapWindow(d, win);
    while (!done) {
        XEvent ev;
        XNextEvent(d, &ev);
        if (ev.type == Expose && ev.xexpose.count == 0) {
            paint(d, win, gc, cm, rels, nelems, w, h, bgpix);
        } else if (ev.type == KeyPress) {
            char buf[16];
            KeySym key;
            XLookupString(&ev.xkey, buf, sizeof(buf), &key, NULL);
            if (key == XK_Escape || buf[0] == 'q')
                done = 1;
        } else if (ev.type == ButtonPress) {
            int i, x = ev.xbutton.x, y = ev.xbutton.y;
            for (i = 0; i < nelems; i++) {
                Resolved *r = &rels[i];
                if (r->kind == E_BUTTON && x >= r->a && y >= r->b &&
                    x < r->a + r->c && y < r->b + r->d) {
                    gui_fire(ip, r->action, r->msg);
                    break;
                }
            }
        } else if (ev.type == ClientMessage &&
                   (Atom)ev.xclient.data.l[0] == wm_delete) {
            done = 1;
        }
    }
    XFreeGC(d, gc);
    XDestroyWindow(d, win);
    XFreeColors(d, cm, &bgpix, 1, 0);
    XCloseDisplay(d);
    free(rels);
    return 1;
}

#else /* no X11 headers: behave like the stub */

int gui_available(void) {
    return 0;
}

int gui_show(Interp *ip, Element *elems, int nelems, int w, int h,
             const char *title, const unsigned char bg[3]) {
    (void)ip;
    (void)elems;
    (void)nelems;
    (void)w;
    (void)h;
    (void)title;
    (void)bg;
    return 0;
}

#endif
