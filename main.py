import flet as ft
import logging
import sys
import threading
import time
import traceback

LOGS = []


class _H(logging.Handler):
    def emit(self, record):
        try:
            LOGS.append("LOG[%s] %s" % (record.levelname, self.format(record)))
        except Exception:
            pass


_h = _H()
_h.setLevel(logging.WARNING)
logging.getLogger().addHandler(_h)


def _thread_hook(args):
    LOGS.append("THREAD ERROR:\n" + "".join(
        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


threading.excepthook = _thread_hook


def _show_status(page, title):
    try:
        info = [title, "views=%d" % len(page.views)]
        for i, v in enumerate(page.views):
            info.append("view%d route=%s controls=%d" % (i, v.route, len(v.controls)))
        info.append("overlay=%d" % len(page.overlay))
        info.append("window=%sx%s" % (page.width, page.height))
        info.extend(LOGS[-8:])
        page.overlay.append(ft.Container(
            bottom=0, left=0, right=0,
            bgcolor="#CC000000",
            padding=10,
            content=ft.Text("\n".join(info), selectable=True, color="yellow", size=11)))
        page.update()
    except Exception:
        pass


def main(page: ft.Page):
    page.on_error = lambda e: LOGS.append("PAGE ERROR: %s" % getattr(e, "data", e))
    page.scroll = ft.ScrollMode.AUTO
    page.add(ft.Text("جاري التحميل...", size=18))
    page.update()
    try:
        import app
        page.controls.clear()
        page.update()
        app.main(page)
    except BaseException:
        page.views.clear()
        page.controls.clear()
        page.add(ft.Container(
            padding=ft.padding.only(top=40, left=10, right=10),
            content=ft.Text(traceback.format_exc(), selectable=True, color="red", size=12)))
        page.update()
        return

    def later():
        time.sleep(4)
        _show_status(page, "STATUS after 4s")

    threading.Thread(target=later, daemon=True).start()


ft.app(target=main, assets_dir="assets")
