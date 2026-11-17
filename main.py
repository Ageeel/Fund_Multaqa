import flet as ft


def main(page: ft.Page):
    page.scroll = ft.ScrollMode.AUTO
    page.add(ft.Text("جاري التحميل...", size=18))
    page.update()
    try:
        import app
        page.controls.clear()
        page.update()
        app.main(page)
    except BaseException:
        import traceback
        page.views.clear()
        page.controls.clear()
        page.add(ft.Container(
            padding=ft.padding.only(top=40, left=10, right=10),
            content=ft.Text(traceback.format_exc(), selectable=True, color="red", size=12)))
        page.update()


ft.app(target=main, assets_dir="assets")
