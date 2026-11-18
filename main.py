import flet as ft
import traceback


def main(page: ft.Page):
    status = ft.Text("اضغط زراً واحداً في كل مرة", size=14, selectable=True)

    def say(msg):
        status.value = msg
        page.update()

    def guard(name, fn):
        def handler(e):
            try:
                say("جارٍ: " + name)
                fn()
                say("تم: " + name + "  (الشاشة ما زالت ظاهرة)")
            except BaseException:
                say("خطأ في " + name + ":\n" + traceback.format_exc())
        return handler

    def t_view():
        page.views.clear()
        page.views.append(ft.View("/", controls=[ft.Text("view ok", size=20), ft.ElevatedButton("رجوع", on_click=lambda e: back())]))
        page.update()

    def back():
        page.views.clear()
        page.views.append(ft.View("/", controls=[col]))
        page.update()

    def t_bg():
        from core import theme
        page.bgcolor = theme.BG
        page.update()

    def t_theme():
        from core import theme
        page.theme = theme.base_theme()
        page.update()

    def t_fonts():
        page.fonts = {"font": "ar.ttf"}
        page.update()

    def t_rtl():
        page.rtl = True
        page.update()

    def t_padding():
        page.padding = 0
        page.update()

    def t_gradient():
        from core import theme
        page.views.append(ft.View("/g", controls=[
            ft.Container(height=120, border_radius=20, padding=20,
                         gradient=ft.LinearGradient(begin=ft.alignment.top_left, end=ft.alignment.bottom_right, colors=theme.GRADIENT_HEADER),
                         content=ft.Text("gradient", color="white")),
            ft.ElevatedButton("رجوع", on_click=lambda e: back())]))
        page.update()

    def t_stack():
        lv = ft.ListView(expand=True, spacing=8, controls=[ft.Text("عنصر %d" % i) for i in range(20)])
        page.views.append(ft.View("/s", controls=[
            ft.Stack(expand=True, controls=[ft.Column([ft.Text("header"), lv], spacing=12)]),
            ]))
        page.update()

    def t_full():
        import app
        page.views.clear()
        page.controls.clear()
        app.main(page)

    names = [
        ("1) واجهة View بسيطة", t_view),
        ("2) لون الخلفية", t_bg),
        ("3) الثيم", t_theme),
        ("4) الخط ar.ttf", t_fonts),
        ("5) RTL", t_rtl),
        ("6) padding=0", t_padding),
        ("7) Gradient", t_gradient),
        ("8) Stack + ListView", t_stack),
        ("9) التطبيق كاملاً", t_full),
    ]
    col = ft.Column(
        [ft.Text("اختبار تشخيصي", size=20, weight="bold"), status]
        + [ft.ElevatedButton(n, on_click=guard(n, f)) for n, f in names],
        scroll=ft.ScrollMode.AUTO, spacing=8)
    page.padding = ft.padding.only(top=40, left=10, right=10)
    page.add(col)


ft.app(target=main, assets_dir="assets")
