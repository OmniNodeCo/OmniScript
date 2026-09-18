/* Windows on Windows, through Win32. */
#include "omni.h"

#ifdef _WIN32

#include <stdlib.h>
#include <windows.h>

typedef struct {
    ElemKind kind;
    int a, b, c, d, e;
    COLORREF col;
    const char *msg;
    Node *action;
} Resolved;

static Interp *G_ip;
static Resolved *G_els;
static int G_nels, G_w, G_h;
static COLORREF G_bg;

static int text_scale(int size) {
    return size < 7 ? 1 : size / 7;
}

static void resolve_all(Interp *ip, Element *elems, int nelems, Resolved *out) {
    int i;
    for (i = 0; i < nelems; i++) {
        Element *el = &elems[i];
        Resolved *r = &out[i];
        unsigned char col[3];
        r->kind = el->kind;
        r->msg = NULL;
        r->action = NULL;
        switch (el->kind) {
        case E_RECT:
            r->a = elem_num(el->slot[0], 0, "rect's x", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "rect's y", el->line, ip);
            r->c = elem_num(el->slot[2], 0, "rect's width", el->line, ip);
            r->d = elem_num(el->slot[3], 0, "rect's height", el->line, ip);
            elem_rgb(el->slot[4], el->line, "#58a6ff", col, ip);
            r->col = RGB(col[0], col[1], col[2]);
            break;
        case E_CIRCLE:
            r->a = elem_num(el->slot[0], 0, "circle's x", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "circle's y", el->line, ip);
            r->c = elem_num(el->slot[2], 0, "circle's radius", el->line, ip);
            elem_rgb(el->slot[3], el->line, "#58a6ff", col, ip);
            r->col = RGB(col[0], col[1], col[2]);
            break;
        case E_LINE:
            r->a = elem_num(el->slot[0], 0, "line's x1", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "line's y1", el->line, ip);
            r->c = elem_num(el->slot[2], 0, "line's x2", el->line, ip);
            r->d = elem_num(el->slot[3], 0, "line's y2", el->line, ip);
            r->e = elem_num(el->slot[5], 1, "line's width", el->line, ip);
            elem_rgb(el->slot[4], el->line, "#58a6ff", col, ip);
            r->col = RGB(col[0], col[1], col[2]);
            break;
        case E_TEXT:
            r->a = elem_num(el->slot[0], 0, "text's x", el->line, ip);
            r->b = elem_num(el->slot[1], 0, "text's y", el->line, ip);
            r->c = elem_num(el->slot[4], 14, "text's size", el->line, ip);
            r->msg = elem_str(el->slot[2], "", ip);
            elem_rgb(el->slot[3], el->line, "#58a6ff", col, ip);
            r->col = RGB(col[0], col[1], col[2]);
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

static void draw_text(HDC dc, int x, int y, const char *s, COLORREF col,
                      int size) {
    int scale = text_scale(size), i, r, q;
    for (i = 0; s[i]; i++) {
        for (r = 0; r < 7; r++) {
            for (q = 0; q < 5; q++) {
                if (font_pixel(s[i], q, r)) {
                    RECT cell;
                    cell.left = x + (i * 6 + q) * scale;
                    cell.top = y + r * scale;
                    cell.right = cell.left + scale;
                    cell.bottom = cell.top + scale;
                    SetBkColor(dc, col);
                    ExtTextOutA(dc, 0, 0, ETO_OPAQUE, &cell, "", 0, NULL);
                }
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

static void paint(HDC dc) {
    int i;
    RECT all;
    HBRUSH bgbrush;
    all.left = 0;
    all.top = 0;
    all.right = G_w;
    all.bottom = G_h;
    bgbrush = CreateSolidBrush(G_bg);
    FillRect(dc, &all, bgbrush);
    DeleteObject(bgbrush);
    for (i = 0; i < G_nels; i++) {
        Resolved *r = &G_els[i];
        switch (r->kind) {
        case E_RECT: {
            RECT rc;
            HBRUSH b = CreateSolidBrush(r->col);
            rc.left = r->a;
            rc.top = r->b;
            rc.right = r->a + (r->c > 0 ? r->c : 0);
            rc.bottom = r->b + (r->d > 0 ? r->d : 0);
            FillRect(dc, &rc, b);
            DeleteObject(b);
            break;
        }
        case E_CIRCLE: {
            HBRUSH b = CreateSolidBrush(r->col);
            HGDIOBJ oldpen = SelectObject(dc, GetStockObject(NULL_PEN));
            HGDIOBJ oldbrush = SelectObject(dc, b);
            if (r->c >= 0)
                Ellipse(dc, r->a - r->c, r->b - r->c, r->a + r->c + 1,
                        r->b + r->c + 1);
            SelectObject(dc, oldpen);
            SelectObject(dc, oldbrush);
            DeleteObject(b);
            break;
        }
        case E_LINE: {
            HPEN pen = CreatePen(PS_SOLID, r->e > 0 ? r->e : 1, r->col);
            HGDIOBJ old = SelectObject(dc, pen);
            MoveToEx(dc, r->a, r->b, NULL);
            LineTo(dc, r->c, r->d);
            SelectObject(dc, old);
            DeleteObject(pen);
            break;
        }
        case E_TEXT:
            draw_text(dc, r->a, r->b, r->msg, r->col, r->c);
            break;
        case E_BUTTON: {
            RECT rc;
            HBRUSH face = CreateSolidBrush(RGB(0x21, 0x26, 0x2d));
            HBRUSH edge = CreateSolidBrush(RGB(0x8b, 0x94, 0x9e));
            int size = r->d - 8, tx, ty;
            if (size > 14)
                size = 14;
            if (size < 8)
                size = 8;
            rc.left = r->a;
            rc.top = r->b;
            rc.right = r->a + (r->c > 0 ? r->c : 0);
            rc.bottom = r->b + (r->d > 0 ? r->d : 0);
            FillRect(dc, &rc, face);
            FrameRect(dc, &rc, edge);
            DeleteObject(face);
            DeleteObject(edge);
            tx = r->a + (r->c - label_width(r->msg, size)) / 2;
            ty = r->b + (r->d - 7 * text_scale(size)) / 2;
            if (tx < r->a + 4)
                tx = r->a + 4;
            if (ty < r->b + 2)
                ty = r->b + 2;
            draw_text(dc, tx, ty, r->msg, RGB(255, 255, 255), size);
            break;
        }
        default:
            break;
        }
    }
}

static LRESULT CALLBACK wndproc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(hwnd, &ps);
        paint(dc);
        EndPaint(hwnd, &ps);
        return 0;
    }
    if (msg == WM_LBUTTONDOWN) {
        int x = LOWORD(lp), y = HIWORD(lp), i;
        for (i = 0; i < G_nels; i++) {
            Resolved *r = &G_els[i];
            if (r->kind == E_BUTTON && x >= r->a && y >= r->b &&
                x < r->a + r->c && y < r->b + r->d) {
                gui_fire(G_ip, r->action, r->msg);
                break;
            }
        }
        return 0;
    }
    if (msg == WM_KEYDOWN && (wp == VK_ESCAPE || wp == 'Q')) {
        DestroyWindow(hwnd);
        return 0;
    }
    if (msg == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

int gui_available(void) {
    return 1;
}

int gui_show(Interp *ip, Element *elems, int nelems, int w, int h,
             const char *title, const unsigned char bg[3]) {
    WNDCLASSA cls;
    HWND hwnd;
    RECT rc;
    MSG msg;
    G_els = malloc(sizeof(Resolved) * (size_t)(nelems + 1));
    if (!G_els)
        return 0;
    resolve_all(ip, elems, nelems, G_els);   /* may fail before GDI opens */
    G_ip = ip;
    G_nels = nelems;
    G_w = w;
    G_h = h;
    G_bg = RGB(bg[0], bg[1], bg[2]);
    memset(&cls, 0, sizeof(cls));
    cls.lpfnWndProc = wndproc;
    cls.hInstance = GetModuleHandleA(NULL);
    cls.lpszClassName = "OmniScript";
    cls.hCursor = LoadCursorA(NULL, IDC_ARROW);
    if (!RegisterClassA(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        free(G_els);
        return 0;
    }
    rc.left = 0;
    rc.top = 0;
    rc.right = w;
    rc.bottom = h;
    AdjustWindowRect(&rc, WS_OVERLAPPEDWINDOW, FALSE);
    hwnd = CreateWindowExA(0, "OmniScript", title, WS_OVERLAPPEDWINDOW,
                           CW_USEDEFAULT, CW_USEDEFAULT, rc.right - rc.left,
                           rc.bottom - rc.top, NULL, NULL, cls.hInstance, NULL);
    if (!hwnd) {
        free(G_els);
        return 0;
    }
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    while (GetMessageA(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    free(G_els);
    G_els = NULL;
    return 1;
}

#else /* not Windows: behave like the stub */

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
