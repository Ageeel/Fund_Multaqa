import flet as ft
import requests
import json
import threading
import os
from core.state import AppState
from core import theme
from datetime import datetime
from notifications import get_notifications_view, build_notification_icon

# --- الثوابت ---
DB_URL = "https://alwafa-afcc1-default-rtdb.firebaseio.com/sub.json"
START_DATE = datetime(2026, 6, 12)
today = datetime.now()
total_fridays = (today - START_DATE).days // 7

def main(page: ft.Page):
    state = AppState(page)
    page.title = state.loc.t("app_name")
    page.rtl = state.loc.rtl
    page.bgcolor = theme.BG
    page.fonts = {"font": "font/ar.ttf"}
    page.theme = theme.base_theme()
    page.padding = 0

    cached_data = page.client_storage.get("data_cache")
    all_data = cached_data if cached_data else {}

    is_offline = False
    view_mode = "active"
    members_list = ft.ListView(expand=True, spacing=0)

    # قفل لمنع تداخل الخيوط وتكرار عناصر القائمة
    render_lock = threading.Lock()

    total_balance_text_header = ft.Text("0", size=20, weight="bold", color=theme.PRIMARY_LIGHT)
    total_balance_text_body = ft.Text("0", size=16, weight="bold", color=theme.TEXT_PRIMARY)
    total_retracted = ft.Text("0", size=16, weight="bold", color=theme.TEXT_PRIMARY)

    loading_text = ft.Text(state.loc.t("loading"), color=theme.TEXT_PRIMARY, size=16, weight="bold")
    loading_overlay = ft.Container(
        visible=False,
        bgcolor=ft.colors.with_opacity(0.85, theme.BG),
        alignment=ft.alignment.center,
        expand=True,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.ProgressRing(color=theme.PRIMARY),
                loading_text
            ]
        )
    )

    refresh_button = ft.FloatingActionButton(
        icon=ft.icons.REFRESH,
        bgcolor=theme.PRIMARY,
        on_click=lambda e: load_data(),
        width=40,
        height=40,
        visible=False
    )

    # ---------------- Payment progress bar (new feature) ----------------
    progress_bar = ft.ProgressBar(value=0, color=theme.PRIMARY, bgcolor=theme.SURFACE_ALT, height=8, border_radius=10)
    progress_label = ft.Text("0%", size=12, color=theme.TEXT_SECONDARY, weight="bold")
    progress_title = ft.Text(state.loc.t("progress"), size=12, color=theme.TEXT_SECONDARY)
    progress_row = ft.Column(
        spacing=4,
        controls=[
            ft.Row([progress_title, progress_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            progress_bar,
        ]
    )

    class Tools(ft.Container):
        def __init__(self, on_click_members=None, on_click_pending=None):
            super().__init__()
            self.total_members = ft.Text("0", color=ft.colors.GREY_300, size=24, weight="bold")
            self.paid_members = ft.Text("0", color=theme.PRIMARY_LIGHT, size=24, weight="bold")
            self.pending_members = ft.Text("0", color=theme.GOLD, size=24, weight="bold")

            self.subs_label = ft.Text(state.loc.t("subscribers"), color=ft.colors.GREY_300, size=12)
            self.payers_label = ft.Text(state.loc.t("payers"), color=theme.PRIMARY_LIGHT, size=12)
            self.dunnes_label = ft.Text(state.loc.t("dunnes"), color=theme.GOLD, size=12)

            self.content = ft.Row(
                spacing=5,
                controls=[
                    self.tool_item(self.subs_label, self.total_members, on_click=on_click_members),
                    self.tool_item(self.payers_label, self.paid_members),
                    self.tool_item(self.dunnes_label, self.pending_members, on_click=on_click_pending)
                ]
            )

        def tool_item(self, label_control, counter, on_click=None):
            return ft.Container(
                expand=True,
                height=80,
                bgcolor=theme.SURFACE,
                border_radius=8,
                padding=10,
                on_click=on_click,
                content=ft.Column(
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[label_control, counter]
                ),
                gradient=ft.LinearGradient(begin=ft.alignment.bottom_center, end=ft.alignment.top_center, colors=theme.GRADIENT_TILE)
            )

        def update_stats(self, total, paid, pending):
            self.total_members.value = str(total)
            self.paid_members.value = str(paid)
            self.pending_members.value = str(pending)

        def apply_language(self):
            self.subs_label.value = state.loc.t("subscribers")
            self.payers_label.value = state.loc.t("payers")
            self.dunnes_label.value = state.loc.t("dunnes")

    def switch_to_active(e):
        nonlocal view_mode
        if view_mode != "active":
            view_mode = "active"
            render_data(all_data, search_field.value)

    def switch_to_retracted(e):
        nonlocal view_mode
        if view_mode != "retracted":
            view_mode = "retracted"
            render_data(all_data, search_field.value)

    def switch_to_pending(e):
        nonlocal view_mode
        if view_mode != "pending":
            view_mode = "pending"
            render_data(all_data, search_field.value)

    tools_section = Tools(on_click_members=switch_to_active, on_click_pending=switch_to_pending)
    search_field = ft.TextField(
        hint_text=state.loc.t("search"),
        hint_style=ft.TextStyle(color=ft.colors.GREY_600, size=14),
        prefix_icon=ft.icons.SEARCH,
        bgcolor=theme.SURFACE,
        color=theme.TEXT_PRIMARY,
        border=ft.InputBorder.NONE,
        border_radius=20,
        content_padding=14,
        on_change=lambda e: render_data(all_data, e.control.value)
    )

    def get_total_amounts(type):
        total_amount = 0
        notif_data = page.client_storage.get("notifications_cache")
        if notif_data and isinstance(notif_data, dict):
            for key, val in notif_data.items():
                if isinstance(val, dict) and val.get("type") == f"{type}":
                    total_amount += val.get("amount", 0)
        return total_amount

    def render_data(data, query=""):
        with render_lock:  # قفل لمنع تداخل عمليات الرسم والتكرار
            members_list.controls.clear()
            total, paid, pending, retracted_count, total_balance = 0, 0, 0, 0, 0

            total_withdrawals = get_total_amounts("w") if data else 0
            total_donations = get_total_amounts("don") if data else 0

            if data:
                now = today

                for key, val in data.items():
                    if not isinstance(val, dict):
                        continue

                    is_retracted = val.get('ret') == True
                    if is_retracted:
                        retracted_count += 1
                    else:
                        total += 1
                        total_balance += val.get("amount", 0)

                        start_str = val.get("start_date", "2026-06-19")
                        try:
                            start_date = datetime.strptime(start_str, "%Y-%m-%d")
                            fridays_passed = (now - start_date).days // 7
                        except ValueError:
                            fridays_passed = 0

                        balance = val.get("total_paid", 0) - fridays_passed
                        is_pending = balance < 0

                        if is_pending:
                            pending += 1
                        else:
                            paid += 1

                    if view_mode == "retracted" and not is_retracted:
                        continue
                    if view_mode in ["active", "pending"] and is_retracted:
                        continue
                    if view_mode == "pending" and not is_pending:
                        continue

                    if query and query not in val.get("name", ""):
                        continue

                    if view_mode == "retracted":
                        members_list.controls.append(
                            ft.ListTile(
                                leading=ft.CircleAvatar(
                                    content=ft.Icon(ft.icons.PERSON_OFF, color=theme.DANGER),
                                    bgcolor=theme.SURFACE
                                ),
                                title=ft.Text(val.get("name", state.loc.t("unknown_name")), color=ft.colors.GREY_400),
                                subtitle=ft.Text(state.loc.t("withdrawn_status"), color=theme.DANGER, size=13)
                            )
                        )
                    else:
                        if balance < 0:
                            status_text = state.loc.t("late_status", n=abs(balance))
                        elif balance == 0:
                            status_text = state.loc.t("paid_status")
                        else:
                            status_text = state.loc.t("advance_status", n=balance)
                        icon = ft.icons.CANCEL if balance < 0 else ft.icons.CHECK_CIRCLE
                        icon_color = theme.GOLD if balance < 0 else theme.PRIMARY_LIGHT

                        if is_offline:
                            profile_img = "user.png"
                        else:
                            profile_img = val.get("img") or "user.png"

                        m_value = val.get("m", 0)
                        if m_value == 1:
                            border_color = theme.PRIMARY
                        elif m_value == 2:
                            border_color = theme.PRIMARY_DARK
                        else:
                            border_color = theme.GOLD_SOFT

                        members_list.controls.append(
                            ft.ListTile(
                                leading=ft.Container(
                                    content=ft.CircleAvatar(
                                        content=ft.Image(
                                            src=profile_img,
                                            fit=ft.ImageFit.COVER,
                                            border_radius=50
                                        ),
                                        bgcolor=theme.SURFACE,
                                    ),
                                    border=ft.border.all(1.5, border_color),
                                    border_radius=50,
                                    padding=2
                                ),
                                title=ft.Text(val.get("name", state.loc.t("unknown_name")), color=ft.colors.GREY_200),
                                subtitle=ft.Text(status_text, color=ft.colors.GREY_500, size=13),
                                trailing=ft.Icon(icon, color=icon_color),
                                on_click=lambda _, contact=val.get("contact"): page.launch_url(contact) if contact else None
                            )
                        )
            if not members_list.controls:
                if view_mode == "pending":
                    empty_msg = state.loc.t("no_pending")
                elif view_mode == "retracted":
                    empty_msg = state.loc.t("no_retracted")
                else:
                    empty_msg = state.loc.t("no_subs")
                members_list.controls.append(
                    ft.Container(
                        padding=20,
                        alignment=ft.alignment.center,
                        content=ft.Text(empty_msg, color=ft.colors.GREY_500, size=16, weight="bold")
                    )
                )

            tools_section.update_stats(total, paid, pending)
            display_val = f"{(total_balance - total_withdrawals):,.0f}"
            total_balance_text_header.value = display_val
            total_balance_text_body.value = f"{total_donations:,.0f}"
            total_retracted.value = str(retracted_count)

            active_total = paid + pending
            ratio = (paid / active_total) if active_total else 0
            progress_bar.value = ratio
            progress_label.value = f"{ratio * 100:,.0f}%"

            try:
                page.update()
            except Exception:
                pass

    def load_data(e=None):
        refresh_button.visible = False
        loading_overlay.visible = True
        try:
            page.update()
        except Exception:
            pass

        def fetch_data():
            nonlocal all_data, is_offline
            try:
                res = requests.get(DB_URL, timeout=5)
                if res.status_code == 200 and res.json():
                    all_data = res.json()
                    is_offline = False
                    try:
                        page.client_storage.set("data_cache", all_data)
                    except Exception:
                        pass
            except Exception as err:
                print("Fetch error:", err)
                is_offline = True
                if not all_data:
                    all_data = page.client_storage.get("data_cache") or {}

            loading_overlay.visible = False
            refresh_button.visible = True
            render_data(all_data, search_field.value)
            try:
                page.update()
            except Exception:
                pass

        threading.Thread(target=fetch_data, daemon=True).start()

    def close_onboarding(e):
        try:
            page.client_storage.set("onboarding_seen", "true")
        except Exception:
            pass
        onboarding_container.visible = False
        refresh_button.visible = True
        try:
            page.update()
        except Exception:
            pass
        load_data()

    onboarding_icon = ft.Icon(ft.icons.SAVINGS_ROUNDED, size=60, color=theme.PRIMARY)
    onboarding_text_ctrl = ft.Text(state.loc.t("onboarding_text"), size=20, color=ft.colors.GREY_300, text_align=ft.TextAlign.CENTER)
    onboarding_sub_ctrl = ft.Text(state.loc.t("onboarding_sub"), size=16, color=theme.TEXT_SECONDARY, text_align=ft.TextAlign.CENTER)
    onboarding_btn_ctrl = ft.ElevatedButton(
        state.loc.t("get_started"), on_click=close_onboarding,
        style=ft.ButtonStyle(bgcolor=theme.PRIMARY, color=theme.BG)
    )

    onboarding_container = ft.Container(
        visible=False,
        bgcolor=theme.BG,
        alignment=ft.alignment.center,
        expand=True,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                onboarding_icon,
                ft.Container(height=10),
                onboarding_text_ctrl,
                onboarding_sub_ctrl,
                ft.Container(height=15),
                onboarding_btn_ctrl
            ]
        )
    )

    # ---------------- Language switcher (new feature) ----------------
    lang_dialog = ft.AlertDialog(modal=True)

    def pick_language(lang):
        def handler(e):
            close_lang_dialog(e)
            apply_language(lang)
        return handler

    def close_lang_dialog(e=None):
        lang_dialog.open = False
        try:
            page.update()
        except Exception:
            pass

    def open_lang_dialog(e=None):
        lang_dialog.title = ft.Text(state.loc.t("choose_language"), color=theme.TEXT_PRIMARY)
        lang_dialog.bgcolor = theme.SURFACE
        lang_dialog.content = ft.Column(
            tight=True,
            controls=[
                ft.ListTile(
                    title=ft.Text(state.loc.t("arabic"), color=theme.TEXT_PRIMARY),
                    leading=ft.Icon(ft.icons.CHECK, color=theme.PRIMARY) if state.loc.lang == "ar" else None,
                    on_click=pick_language("ar")
                ),
                ft.ListTile(
                    title=ft.Text(state.loc.t("english"), color=theme.TEXT_PRIMARY),
                    leading=ft.Icon(ft.icons.CHECK, color=theme.PRIMARY) if state.loc.lang == "en" else None,
                    on_click=pick_language("en")
                ),
            ]
        )
        lang_dialog.actions = [ft.TextButton(state.loc.t("close"), on_click=close_lang_dialog)]
        page.dialog = lang_dialog
        lang_dialog.open = True
        try:
            page.update()
        except Exception:
            pass

    def apply_language(lang):
        if lang == state.loc.lang:
            return
        state.set_lang(lang)
        page.rtl = state.loc.rtl
        page.title = state.loc.t("app_name")

        search_field.hint_text = state.loc.t("search")
        loading_text.value = state.loc.t("loading")
        progress_title.value = state.loc.t("progress")
        tools_section.apply_language()

        onboarding_text_ctrl.value = state.loc.t("onboarding_text")
        onboarding_sub_ctrl.value = state.loc.t("onboarding_sub")
        onboarding_btn_ctrl.text = state.loc.t("get_started")

        render_data(all_data, search_field.value)
        route_change(page.route)
        try:
            page.update()
        except Exception:
            pass

    def route_change(route):
        page.views.clear()

        retracted_container = ft.Container(
            on_click=switch_to_retracted,
            content=ft.Column(
                [ft.Text(state.loc.t("retracted"), size=14, color=ft.colors.GREY_300), total_retracted],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )
        )

        header_top_row = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row([ft.Text(state.loc.t("sub_funds"), size=18, color=theme.GOLD), total_balance_text_header, ft.Text(state.loc.t("£"), size=18, color=theme.PRIMARY_LIGHT)], spacing=3),
                ft.Row(
                    spacing=0,
                    controls=[
                        ft.IconButton(icon=ft.icons.TRANSLATE, icon_color=ft.colors.GREY_400, tooltip=state.loc.t("language"), on_click=open_lang_dialog),
                        build_notification_icon(page),
                    ]
                )
            ]
        )

        header = ft.Card(
            margin=ft.margin.all(0),
            elevation=5,
            content=ft.Container(
                padding=20,
                border_radius=10,
                gradient=ft.LinearGradient(begin=ft.alignment.bottom_left, end=ft.alignment.top_right, colors=theme.GRADIENT_HEADER),
                content=ft.Column(
                    spacing=10,
                    controls=[
                        header_top_row,
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                            controls=[
                                ft.Column([ft.Text(state.loc.t("fridays"), size=14, color=ft.colors.GREY_300), ft.Text(str(total_fridays), size=16, weight="bold", color=ft.colors.GREY_300)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                ft.VerticalDivider(),
                                ft.Column([ft.Text(state.loc.t("donations"), size=14, color=ft.colors.GREY_300), total_balance_text_body], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                ft.VerticalDivider(),
                                retracted_container
                            ]
                        ),
                        ft.Container(height=4),
                        progress_row,
                    ]
                )
            )
        )

        page.views.append(
            ft.View(
                "/",
                bgcolor=theme.BG,
                padding=ft.padding.only(top=50, left=15, right=15),
                controls=[ft.Stack(expand=True, controls=[ft.Column([header, tools_section, search_field, members_list], spacing=5), loading_overlay, onboarding_container])],
                floating_action_button=refresh_button
            )
        )

        if page.route == "/notifications":
            page.views.append(get_notifications_view(page))

        try:
            page.update()
        except Exception:
            pass

    page.on_route_change = route_change
    page.go("/")

    # التحقق من حالة الترحيب ومنع تكرار استدعاء التحميل عند البدء
    if not page.client_storage.get("onboarding_seen"):
        onboarding_container.visible = True
        try:
            page.update()
        except Exception:
            pass
    else:
        refresh_button.visible = True
        if all_data:
            render_data(all_data, search_field.value)
        load_data()


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
