# app_5.py (updated)
import streamlit as st
import os, datetime, re, json, logging, random, string
from dotenv import load_dotenv
from google.generativeai import GenerativeModel, configure
from helpers import (
    is_valid_booking_date as validate_date,
    generate_time_slots,
    send_email,
    write_confirm_email_v2,
    write_cancel_email_v2,
    choose_doctor
)
from db import find_available_doctors, get_all_doctors, get_available_slots, format_slots_human_readable
from email_settings import from_email_default, password_default, sdt

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

# ====== Setup ======
load_dotenv()
configure(api_key=os.getenv("GEMINI_API_KEY_1"))
model = GenerativeModel("gemini-2.5-flash-lite")

st.set_page_config(page_title="Chatbot Đặt lịch khám", layout="centered")
st.title("🤖 Chatbot Đặt lịch khám")

# ====== Init session_state ======
for key, default in {
    "messages": [],
    "booking_info": {},
    "show_booking_form": False,
    "disable_chat_input": False,
    "booking_done": False,
    "cancel_mode": False,
    "last_doctor_list": None  # lưu danh sách bác sĩ gần nhất bot vừa show
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ====== Helper ======
def add_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})
    with st.chat_message(role):
        st.write(content)

def toggle_chat_input(flag: bool):
    st.session_state.disable_chat_input = flag


# ====== Intent classification ======
def classify_intent(user_text: str) -> str:
    text = user_text.lower().strip()

    booking_kw = ["đặt lịch", "muốn đặt", "book", "đăng ký", "muốn khám", "hẹn khám", "đặt khám"]
    doctor_kw = ["danh sách bác sĩ", "những bác sĩ", "có bác sĩ nào", "ai là bác sĩ",
                 "ngày khám", "lịch khám", "xem lịch", "còn trống", "rảnh", "lịch của", "lịch trống",
                 "bác sĩ số", "phòng khám"]
    chitchat_kw = ["xin chào", "hi", "hello", "cảm ơn", "thanks", "ok", "được", "chào"]

    if any(k in text for k in chitchat_kw):
        return "chitchat"
    if any(k in text for k in booking_kw):
        return "booking_request"
    if any(k in text for k in doctor_kw):
        return "doctor_info"

    # fallback dùng model
    try:
        prompt = f"""
        Bạn là hệ thống phân loại intent.
        Văn bản: "{user_text}"
        Nếu người dùng muốn đặt lịch khám => booking_request
        Nếu muốn hỏi bác sĩ, lịch khám, lịch trống => doctor_info
        Nếu không => chitchat
        """
        resp = model.generate_content(prompt)
        return resp.text.strip().lower()
    except Exception as e:
        logging.debug(f"classify_intent fallback error: {e}")
        return "chitchat"


# ====== Extract date & time ======
def extract_datetime(user_text):
    """Dùng Gemini để lấy ngày + giờ từ câu nhập"""
    today = datetime.date.today()
    prompt = f"""
    Trích xuất ngày và giờ từ câu sau.
    Trả về JSON dạng: {{"date": "YYYY-MM-DD" hoặc null, "time": "HH:MM" hoặc null}}.
    Hôm nay là {today.strftime('%Y-%m-%d')}.
    Câu: "{user_text}"
    """
    try:
        resp = model.generate_content(prompt)
        m = re.search(r"\{.*\}", resp.text, re.S)
        if m:
            data = json.loads(m.group())
            return data.get("date"), data.get("time")
    except Exception as e:
        logging.debug(f"extract_datetime error: {e}")
    return None, None


# ====== Hiển thị lịch sử chat ======
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])


# ====== Input chat ======
if not st.session_state.disable_chat_input and not st.session_state.booking_done:
    user_input = st.chat_input("Nhập tin nhắn...")
else:
    user_input = None


# ====== Xử lý input ======
if user_input:
    add_message("user", user_input)
    intent = classify_intent(user_input)
    logging.debug(f"User input: {user_input} -> intent: {intent}")

    # --- CHITCHAT ---
    if intent == "chitchat":
        try:
            reply = model.generate_content(user_input).text
        except Exception as e:
            logging.debug(f"chitchat model error: {e}")
            reply = "Mình nghe bạn. Bạn muốn làm gì tiếp theo?"
        add_message("assistant", reply)

    # --- DOCTOR INFO ---
    elif intent == "doctor_info":
        doctors = get_all_doctors()
        user_lower = user_input.lower()

        # Nếu người hỏi explicit "danh sách"
        if any(k in user_lower for k in ["danh sách", "những bác sĩ", "có bác sĩ nào", "liệt kê bác sĩ"]):
            reply = "👨‍⚕️ Danh sách bác sĩ:\n"
            for i, doc in enumerate(doctors, 1):
                reply += f"{i}. {doc['name']} (Phòng {doc.get('room','-')})\n"
            add_message("assistant", reply)
            st.session_state.last_doctor_list = doctors
        else:
            # Người dùng có thể hỏi "bác sĩ số 2" hoặc tên bác sĩ + ngày
            # 1) ưu tiên "bác sĩ số X" nếu có last_doctor_list
            m_idx = re.search(r"bác sĩ\s*(?:số\s*)?(\d+)", user_lower)
            chosen = None
            if m_idx and st.session_state.last_doctor_list:
                idx = int(m_idx.group(1)) - 1
                if 0 <= idx < len(st.session_state.last_doctor_list):
                    chosen = st.session_state.last_doctor_list[idx]
                    logging.debug(f"Doctor referenced by index -> {chosen}")

            # 2) nếu chưa có, dùng choose_doctor (tìm theo tên substring)
            if not chosen:
                chosen = choose_doctor(user_input, doctors)
                # choose_doctor có thể trả về list (nhiều kết quả), dict hoặc None
                if isinstance(chosen, list) and len(chosen) > 1:
                    reply = "❌ Có nhiều bác sĩ trùng tên, vui lòng chọn rõ hơn:\n"
                    for i, doc in enumerate(chosen, 1):
                        reply += f"{i}. {doc['name']} (Phòng {doc.get('room','-')})\n"
                    add_message("assistant", reply)
                    st.session_state.last_doctor_list = chosen
                    st.stop()
                elif isinstance(chosen, list) and len(chosen) == 1:
                    chosen = chosen[0]

            if not chosen:
                add_message("assistant", "❌ Mình không tìm thấy bác sĩ phù hợp. Bạn muốn xem danh sách bác sĩ không?")
                st.session_state.last_doctor_list = doctors
                st.stop()

            # Lấy ngày nếu user hỏi (fallback -> hôm nay)
            date_extracted, _ = extract_datetime(user_input)
            if date_extracted:
                target_date = date_extracted
            else:
                target_date = datetime.date.today().strftime("%Y-%m-%d")

            # gọi hàm lấy slots
            chosen_id = chosen.get("id") or chosen.get("doctor_id")
            try:
                slots = get_available_slots(chosen_id, target_date)
            except Exception as e:
                logging.debug(f"get_available_slots error: {e}")
                slots = []

            if not slots:
                add_message("assistant", f"❌ Không có lịch trống cho bác sĩ {chosen.get('name')} vào ngày {target_date}.")
            else:
                reply = f"📅 Lịch trống của bác sĩ {chosen.get('name')} ngày {target_date}:\n"
                try:
                    reply += format_slots_human_readable(slots)
                except Exception:
                    # fallback simple formatting
                    reply += ", ".join([s.get("time", str(s)) for s in slots])
                add_message("assistant", reply)

            st.session_state.last_doctor_list = [chosen]

    # --- BOOKING REQUEST ---
    else:
        # giữ flow booking như cũ: trích xuất date/time rồi mở form
        date_extracted, time_extracted = extract_datetime(user_input)
        if date_extracted:
            st.session_state.booking_info["Ngay"] = date_extracted
        if time_extracted:
            st.session_state.booking_info["Gio"] = f"{time_extracted}:00" if len(time_extracted) == 5 else time_extracted

        st.session_state.show_booking_form = True
        toggle_chat_input(True)
        st.rerun()


# ====== Form đặt lịch ======
if st.session_state.show_booking_form:
    with st.chat_message("assistant"):
        st.write("📅 Vui lòng nhập thông tin đặt lịch:")

        prev_info = st.session_state.booking_info or {}

        # Khoảng ngày hợp lệ: từ ngày mai đến 14 ngày sau
        min_date = datetime.date.today() + datetime.timedelta(days=1)
        max_date = datetime.date.today() + datetime.timedelta(days=14)

        # Kiểm tra ngày có sẵn trong prev_info
        prev_date_str = prev_info.get("Ngay")
        if prev_date_str:
            try:
                parsed_prev_date = datetime.datetime.strptime(prev_date_str, "%Y-%m-%d").date()
            except Exception:
                parsed_prev_date = None

            if parsed_prev_date and (parsed_prev_date < min_date or parsed_prev_date > max_date):
                add_message(
                    "assistant",
                    (
                        f"❌ Ngày bạn yêu cầu **{parsed_prev_date.strftime('%d/%m/%Y')}** không hợp lệ.\n\n"
                        f"Vui lòng nhập lại ngày khám trong khoảng "
                        f"**{min_date.strftime('%d/%m/%Y')}** — **{max_date.strftime('%d/%m/%Y')}** (không tính hôm nay)."
                    )
                )
                st.session_state.booking_info.pop("Ngay", None)
                st.session_state.show_booking_form = True
                toggle_chat_input(True)
                st.rerun()

        # ----- Nếu ngày hợp lệ thì render form -----
        with st.form("booking_form"):
            # Họ tên (bắt buộc)
            name = st.text_input("Họ tên (*)", value=prev_info.get("HoTen", ""))

            # Ngày khám (bắt buộc)
            try:
                default_date = datetime.datetime.strptime(
                    prev_info.get("Ngay", min_date.strftime("%Y-%m-%d")), "%Y-%m-%d"
                ).date()
                if default_date < min_date or default_date > max_date:
                    default_date = min_date
            except Exception:
                default_date = min_date

            date = st.date_input("Ngày khám (*)", value=default_date, min_value=min_date, max_value=max_date)

            # Giờ khám (bắt buộc)
            default_time = datetime.time(9, 0)
            if prev_info.get("Gio"):
                try:
                    default_time = datetime.datetime.strptime(prev_info["Gio"], "%H:%M:%S").time()
                except:
                    try:
                        default_time = datetime.datetime.strptime(prev_info["Gio"], "%H:%M").time()
                    except:
                        pass
            time_slots = generate_time_slots("06:00", "18:00", 30)
            time = st.selectbox(
                "Giờ khám (*)",
                options=time_slots,
                index=time_slots.index(default_time) if default_time in time_slots else 6,
                format_func=lambda t: t.strftime("%H:%M")
            )

            # Chọn bác sĩ (optional)
            doctors = get_all_doctors()
            doctor_names = ["(Không chọn)"] + [f"{d['name']} (Phòng {d.get('room','-')})" for d in doctors]
            doctor_choice = st.selectbox("Bác sĩ (optional)", options=doctor_names)

            # Email (optional)
            email = st.text_input("Email (optional)", value=prev_info.get("email", ""))

            submit = st.form_submit_button("Xác nhận đặt lịch")

        if submit:
            # Validate
            if not name.strip():
                st.error("❌ Họ tên là bắt buộc.")
                st.stop()

            date_str = date.strftime("%Y-%m-%d")
            time_str = time.strftime("%H:%M:%S")

            chosen_doctor = None
            if doctor_choice != "(Không chọn)":
                idx = doctor_names.index(doctor_choice) - 1
                chosen_doctor = doctors[idx]

            # Kiểm tra bác sĩ rảnh
            available = find_available_doctors(date_str, time_str)
            if chosen_doctor:
                available_ids = [d["id"] for d in available]
                if chosen_doctor["id"] not in available_ids:
                    add_message("assistant", f"❌ Bác sĩ {chosen_doctor['name']} không rảnh vào {time.strftime('%H:%M')} {date.strftime('%d/%m/%Y')}. Vui lòng chọn lại.")
                    st.session_state.booking_info = {"HoTen": name, "Ngay": date_str, "Gio": time_str, "email": email}
                    st.session_state.show_booking_form = True
                    toggle_chat_input(True)
                    st.rerun()
            if not available:
                add_message("assistant", f"❌ Không có bác sĩ nào rảnh {time.strftime('%H:%M')} {date.strftime('%d/%m/%Y')}. Vui lòng chọn lại.")
                st.session_state.booking_info = {"HoTen": name, "Ngay": date_str, "email": email}
                st.session_state.show_booking_form = True
                toggle_chat_input(True)
                st.rerun()

            # Tạo mã đặt lịch
            booking_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            st.session_state.booking_info = {
                "MaDatLich": booking_code,
                "HoTen": name,
                "Ngay": date_str,
                "Gio": time_str[:5],
                "doctor_id": chosen_doctor["id"] if chosen_doctor else None,
                "doctor_name": chosen_doctor["name"] if chosen_doctor else "(Chưa chọn)",
                "doctor_room": chosen_doctor["room"] if chosen_doctor else "(Chưa chọn)",
                "email": email,
                "ChiNhanh": "Cơ sở 1",
                "DiaChi": "123 Đường ABC, Quận 1, TP.HCM"
            }

            # Gửi tin nhắn xác nhận
            try:
                d_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                weekday_map = {0: "Thứ Hai", 1: "Thứ Ba", 2: "Thứ Tư", 3: "Thứ Năm", 4: "Thứ Sáu", 5: "Thứ Bảy", 6: "Chủ Nhật"}
                weekday = weekday_map[d_obj.weekday()]
                date_human = d_obj.strftime("%d/%m/%Y")
            except:
                weekday = ""
                date_human = date_str

            summary = (
                "🔔 Xác nhận thông tin đặt lịch:\n"
                f"- Mã đặt lịch: {st.session_state.booking_info['MaDatLich']}\n"
                f"- Họ tên: {st.session_state.booking_info['HoTen']}\n"
                f"- Ngày: {date_human} {f'({weekday})' if weekday else ''}\n"
                f"- Giờ: {st.session_state.booking_info['Gio']}\n"
                f"- Bác sĩ: {st.session_state.booking_info['doctor_name']} (Phòng {st.session_state.booking_info['doctor_room']})\n"
                f"- Cơ sở: {st.session_state.booking_info['ChiNhanh']}\n"
                f"- Địa chỉ: {st.session_state.booking_info['DiaChi']}\n"
            )
            add_message("assistant", summary)

            # Gửi email nếu có
            if email:
                data = {
                    "TenBenhVien": "Hehe Hospital",
                    **st.session_state.booking_info,
                    "Hotline": sdt,
                    "EmailCSKH": "cskh@hehehospital.vn",
                    "ZaloChatLink": "https://zalo.me/hehehospital",
                    "LinkDoiHuy": "https://hehehospital.vn/lichkham",
                    "GioLamViec": "Thứ 2 - Thứ 7: 7h00 - 17h00",
                    "Website": "https://hehehospital.vn"
                }
                try:
                    subject, body = write_confirm_email_v2(data)
                    send_email(email, from_email_default, password_default, subject, body)
                    add_message("assistant", "✅ Email xác nhận đã được gửi tới " + email)
                except Exception as e:
                    logging.debug(f"send_email error: {e}")
                    add_message("assistant", "⚠️ Gửi email thất bại. Tuy nhiên lịch đã được lưu cục bộ.")
            else:
                add_message("assistant", "✅ Lịch khám đã được ghi nhận. (Không có email)")

            st.session_state.booking_done = True
            st.session_state.show_booking_form = False
            toggle_chat_input(False)
            st.rerun()


# ====== Sau khi đã đặt xong: hiện nút Đổi / Huỷ ======
if st.session_state.booking_done and not st.session_state.cancel_mode:
    with st.chat_message("assistant"):
        st.write("📌 Bạn muốn làm gì tiếp theo?")
        c1, c2 = st.columns(2)

        # ---------- Nút Đổi lịch ----------
        if c1.button("🔁 Đổi lịch"):
            st.session_state.show_booking_form = True
            st.session_state.booking_done = False
            toggle_chat_input(True)
            st.rerun()

        # ---------- Nút Huỷ lịch ----------
        if c2.button("❌ Huỷ lịch"):
            st.session_state.cancel_mode = True
            toggle_chat_input(True)
            st.rerun()


# ====== Form hủy lịch ======
if st.session_state.cancel_mode:
    with st.chat_message("assistant"):
        st.write("❌ Vui lòng nhập lý do huỷ lịch:")

        with st.form("cancel_form"):
            cancel_reason = st.text_area("Lý do huỷ (optional)", "")
            confirm_cancel = st.form_submit_button("Xác nhận huỷ")

        if confirm_cancel:
            if st.session_state.booking_info and st.session_state.booking_info.get("email"):
                from datetime import datetime
                data = {
                    "TenBenhVien": "Hehe Hospital",
                    **st.session_state.booking_info,
                    "LyDoHuy": cancel_reason if cancel_reason.strip() else "Người dùng yêu cầu huỷ lịch",
                    "NgayHuy": datetime.now().strftime("%Y-%m-%d"),
                    "Hotline": sdt,
                    "EmailCSKH": "cskh@hehehospital.vn",
                    "ZaloChatLink": "https://zalo.me/hehehospital",
                    "LinkDoiHuy": "https://hehehospital.vn/lichkham",
                    "GioLamViec": "7h30 - 17h00",
                    "Website": "https://hehehospital.vn"
                }
                try:
                    subject, body = write_cancel_email_v2(data)
                    send_email(st.session_state.booking_info["email"], from_email_default, password_default, subject, body)
                except Exception as e:
                    logging.debug(f"send cancel email error: {e}")

            add_message("assistant", "🗑️ Lịch khám đã được huỷ.")
            st.session_state.booking_info = {}
            st.session_state.booking_done = False
            st.session_state.cancel_mode = False
            toggle_chat_input(False)
            st.rerun()
