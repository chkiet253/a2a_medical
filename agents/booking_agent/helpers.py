from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from email_settings import HOST, PORT
import sqlite3
import re
DB_NAME = r"C:\Users\Acer\OneDrive\Desktop\Intern\A2A_Hospital\Booking_Agent\schedule.db"

# ==========================
# Chọn bác sĩ theo số thứ tự hoặc tên
# ==========================
def choose_doctor(user_input: str, doctors: list):
    """
    Trả về:
      - dict bác sĩ nếu tìm 1 match
      - list[dict] nếu nhiều match (cần người dùng chọn rõ hơn)
      - None nếu không tìm
    doctors: list of dict. Accepts dicts with keys 'id'/'doctor_id', 'name', 'room'
    """
    user_lower = user_input.lower()

    # 1) Nếu có pattern "bác sĩ số X" hoặc "bs số X" -> lấy index từ context hoặc list
    m = re.search(r"bác sĩ\s*(?:số\s*)?(\d+)", user_lower)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(doctors):
            return doctors[idx]
        else:
            return None

    # 2) Nếu user chỉ viết 1 số kèm "thứ X" hoặc "số X" không có chữ bác sĩ (ví dụ "số 2")
    m2 = re.search(r"\b(?:số|thứ)\s*(\d+)\b", user_lower)
    if m2 and "ngày" not in user_lower:   # tránh bắt số ngày như "ngày 20"
        idx = int(m2.group(1)) - 1
        if 0 <= idx < len(doctors):
            return doctors[idx]

    # 3) match theo tên (contains, case-insensitive)
    matches = []
    for doc in doctors:
        name = doc.get("name", "").lower()
        if name and name in user_lower:
            matches.append(doc)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return matches  # multiple

    # 4) fallback: exact token match (words)
    tokens = re.findall(r"\w+", user_lower)
    for doc in doctors:
        for tok in tokens:
            if tok and tok in doc.get("name","").lower().split():
                return doc

    return None


# ==========================
# Lấy danh sách thông tin của toàn bộ bác sĩ
# ==========================
def get_all_doctors():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, name, room FROM doctors")
    doctors = cur.fetchall()
    conn.close()
    return [{"id": d[0], "name": d[1], "room": d[2]} for d in doctors]


def get_available_slots(doctor_id: str, date: str):
    """
    Lấy toàn bộ khung giờ còn trống của một bác sĩ trong ngày cụ thể.

    - doctor_id: id bác sĩ
    - date: ngày muốn kiểm tra (YYYY-MM-DD)
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Lấy các ca làm việc cố định trong tuần của bác sĩ
    weekday = str(datetime.strptime(date, "%Y-%m-%d").weekday())  # 0=Mon
    cur.execute("""
        SELECT start_time, end_time
        FROM work_shifts
        WHERE doctor_id = ? AND day_of_week = ?
    """, (doctor_id, weekday))
    base_shifts = cur.fetchall()

    # Lấy các ngoại lệ (nghỉ hoặc tăng ca) trong ngày
    cur.execute("""
        SELECT start_time, end_time, is_available
        FROM shift_exceptions
        WHERE doctor_id = ? AND date = ?
    """, (doctor_id, date))
    exceptions = cur.fetchall()

    # Lấy các cuộc hẹn đã đặt trong ngày (để loại khỏi danh sách trống)
    cur.execute("""
        SELECT start_time, end_time
        FROM appointments
        WHERE doctor_id = ? AND date = ? AND status = 'booked'
    """, (doctor_id, date))
    booked = cur.fetchall()
    conn.close()

    # Ghép lại các ca làm việc có hiệu lực trong ngày đó
    work_periods = []

    # Bắt đầu từ ca cố định
    for s, e in base_shifts:
        work_periods.append((s, e))

    # Xử lý ngoại lệ: nếu is_available=0 (nghỉ) thì xoá, nếu =1 thì thêm
    for s, e, avail in exceptions:
        if avail == 0:
            work_periods = [(ws, we) for ws, we in work_periods if not (ws == s and we == e)]
        else:
            work_periods.append((s, e))

    # Tạo danh sách slot 30 phút từ work_periods, bỏ những slot đã bị đặt
    def time_range(start, end, step=30):
        cur = datetime.strptime(start, "%H:%M")
        end_t = datetime.strptime(end, "%H:%M")
        while cur + timedelta(minutes=step) <= end_t:
            yield cur.strftime("%H:%M"), (cur + timedelta(minutes=step)).strftime("%H:%M")
            cur += timedelta(minutes=step)

    available = []
    for s, e in work_periods:
        for slot_start, slot_end in time_range(s, e):
            # nếu slot này giao với bất kỳ lịch đã đặt -> bỏ qua
            overlap = any(not (slot_end <= b_s or slot_start >= b_e) for b_s, b_e in booked)
            if not overlap:
                available.append((slot_start, slot_end))

    return available

def format_slots_human_readable(slots):
    """
    Nhận danh sách slot [(start_time, end_time), ...]
    và trả về chuỗi text dễ đọc cho người dùng.
    """
    if not slots:
        return "❌ Hiện không còn khung giờ trống nào trong ngày này."

    lines = ["🕒 Các khung giờ trống:"]
    for start, end in slots:
        lines.append(f"- {start} – {end}")
    return "\n".join(lines)



# ==========================
# Chuyển đổi / Định dạng ngày giờ
# ==========================
def weekday_to_name(weekday: int) -> str:
    """
    Đổi số thứ trong tuần (0=Mon...6=Sun) thành tên tiếng Anh
    """
    names = ["Monday", "Tuesday", "Wednesday",
             "Thursday", "Friday", "Saturday", "Sunday"]
    return names[weekday]


def format_time_range(start: str, end: str) -> str:
    """
    Gộp giờ bắt đầu và kết thúc thành 1 chuỗi gọn
    """
    return f"{start[:-3]} - {end[:-3]}"  # Bỏ giây nếu có HH:MM:SS


def parse_datetime(date_str: str, time_str: str) -> datetime:
    """
    Gộp chuỗi ngày (YYYY-MM-DD) và giờ (HH:MM:SS) thành 1 datetime
    """
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")


def is_valid_booking_date(date_str: str) -> bool:
    """
    Kiểm tra ngày có hợp lệ không:
    - Phải lớn hơn hôm nay
    - Không quá 7 ngày tới
    """
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        return today < target <= today + timedelta(days=7)
    except ValueError:
        return False


# Giữ alias cho tương thích cũ nếu app.py gọi validate_date
validate_date = is_valid_booking_date


# ==========================
# Tạo ID 5 chữ số
# ==========================
def generate_appointment_id(latest_id: int) -> str:
    """
    Sinh mã appointment mới từ id lớn nhất hiện tại (số int)
    """
    return f"{latest_id + 1:05d}"


# ==========================
# Tiện ích kiểm tra thời gian
# ==========================
def is_time_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    """
    Kiểm tra hai khoảng thời gian có bị giao nhau không
    """
    return not (end1 <= start2 or start1 >= end2)

# ==========================
# Tạo time cho form
# ==========================
def generate_time_slots(start="06:00", end="18:00", step=30):
    times = []
    current = datetime.strptime(start, "%H:%M")
    end_dt = datetime.strptime(end, "%H:%M")
    while current <= end_dt:
        times.append(current.time())
        current += timedelta(minutes=step)
    return times

# =============================
# Hàm gửi mail
# =============================
def send_email(to_email, from_email, password, subject, body):
    # Tạo server & đăng nhập
    server = smtplib.SMTP(HOST, PORT)
    server.starttls()
    try:
        server.login(from_email, password)
    except smtplib.SMTPAuthenticationError:
        print("Error! Invalid Sender Email or Password!")
        server.quit()
        return

    message = MIMEMultipart()
    message['Subject'] = subject
    message['From'] = from_email
    message['To'] = to_email

    message.attach(MIMEText(body, 'plain'))

    server.sendmail(from_email, to_email, message.as_string())
    server.quit()


# =============================
# Chuẩn hóa ngày về dd/mm/yyyy
# =============================
def format_date_vn(date_value):
    if isinstance(date_value, datetime):
        return date_value.strftime("%d/%m/%Y")
    try:
        return datetime.strptime(date_value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return date_value


# =============================
# Viết nội dung mail xác nhận
# =============================
def write_confirm_email(data):
    data = data.copy()
    data['Ngay'] = format_date_vn(data['Ngay'])

    email_subject = "Xác nhận đặt lịch khám tại Bệnh viện {TenBenhVien} - Mã: {MaDatLich}"

    email_template = """
    Kính gửi: {HoTen},

    Cảm ơn Quý khách đã lựa chọn Bệnh viện {TenBenhVien}.
    Chúng tôi xin thông báo đặt lịch khám của Quý khách đã được xác nhận với thông tin chi tiết như sau:

    Thông tin đặt lịch
    - Mã đặt lịch: {MaDatLich}
    - Họ và tên: {HoTen}
    - Ngày: {Ngay}
    - Giờ: {Gio}
    - Chi nhánh/Địa chỉ: {ChiNhanh} - {DiaChi}

    Trước khi tới khám
    - Vui lòng có mặt trước ít nhất 30 phút để làm thủ tục tiếp nhận.
    - Mang theo: CMND/CCCD/Hộ chiếu, thẻ BHYT (nếu sử dụng), các kết quả xét nghiệm/phiếu khám trước (nếu có).
    - Nếu lịch khám bao gồm xét nghiệm yêu cầu nhịn ăn hoặc chuẩn bị đặc biệt, chúng tôi sẽ có thông báo riêng - vui lòng tuân thủ để kết quả chính xác.
    - Thanh toán: hỗ trợ tiền mặt, thẻ nội địa/quốc tế, và áp dụng BHYT theo quy định (nếu có).

    Hủy / đổi lịch
    - Nếu Quý khách cần hủy hoặc thay đổi lịch, vui lòng liên hệ trước ít nhất 24 giờ (nếu có thể) để chúng tôi sắp xếp.
    - Đổi / hủy qua: Hotline: {Hotline} - Email: {EmailCSKH} - Zalo/Chat: {ZaloChatLink} - Hoặc truy cập đường dẫn: {LinkDoiHuy}

    Lưu ý chăm sóc sức khỏe & an toàn
    - Nếu Quý khách có triệu chứng nhiễm trùng hô hấp (sốt, ho, khó thở), vui lòng thông báo trước để nhân viên sắp xếp khu vực khám phù hợp.
    - Bệnh viện tuân thủ các quy định an toàn y tế; Quý khách vui lòng mang khẩu trang và tuân thủ hướng dẫn của nhân viên.

    Nếu Quý khách cần hỗ trợ thêm, xin vui lòng liên hệ:
    Bệnh viện {TenBenhVien} - Hotline: {Hotline} - Email: {EmailCSKH}
    Thời gian làm việc: {GioLamViec}

    Một lần nữa xin cảm ơn Quý khách. Kính chúc Quý khách sức khỏe và mong được phục vụ!

    Trân trọng,
    Đội ngũ Chăm sóc Khách hàng
    Bệnh viện {TenBenhVien}
    Địa chỉ: {DiaChi} | Website: {Website}
    """

    subject = email_subject.format(**data)
    body = email_template.format(**data)
    return subject, body


# =============================
# Viết nội dung mail hủy lịch
# =============================
def write_cancel_email(data):
    data = data.copy()
    data['Ngay'] = format_date_vn(data['Ngay'])
    data['NgayHuy'] = format_date_vn(data.get('NgayHuy', datetime.now().strftime("%Y-%m-%d")))

    email_subject = "Xác nhận HỦY lịch khám tại Bệnh viện {TenBenhVien} - Mã: {MaDatLich}"

    email_template = """
    Kính gửi: {HoTen},

    Bệnh viện {TenBenhVien} xin xác nhận rằng lịch khám của Quý khách với thông tin sau đã được HỦY:

    Thông tin đặt lịch (đã hủy):
    - Mã đặt lịch: {MaDatLich}
    - Họ và tên: {HoTen}
    - Ngày: {Ngay}
    - Giờ: {Gio}
    - Chi nhánh/Địa chỉ: {ChiNhanh} - {DiaChi}

    Thông tin hủy
    - Lý do (nếu có): {LyDoHuy}
    - Ngày hủy: {NgayHuy}

    Nếu quý khách hủy nhầm hoặc muốn đặt lại lịch, vui lòng liên hệ qua:
    - Hotline: {Hotline}
    - Email: {EmailCSKH}
    - Zalo/Chat: {ZaloChatLink}
    - Hoặc truy cập đường dẫn: {LinkDoiHuy}

    Lưu ý:
    - Nếu lịch có yêu cầu hoàn/hoãn thanh toán hoặc chính sách huỷ riêng, nhân viên CSKH sẽ liên hệ để hướng dẫn cụ thể.
    - Thời gian làm việc CSKH: {GioLamViec}.

    Nếu Quý khách cần hỗ trợ thêm, xin vui lòng liên hệ:
    Bệnh viện {TenBenhVien} - Hotline: {Hotline} - Email: {EmailCSKH}
    Thời gian làm việc: {GioLamViec}

    Một lần nữa xin cảm ơn Quý khách. Kính chúc Quý khách sức khỏe và mong được phục vụ!

    Trân trọng,
    Đội ngũ Chăm sóc Khách hàng
    Bệnh viện {TenBenhVien}
    Địa chỉ: {DiaChi} | Website: {Website}
    """

    subject = email_subject.format(**data)
    body = email_template.format(**data)
    return subject, body


def write_confirm_email_v2(data):
    data = data.copy()
    data['Ngay'] = format_date_vn(data['Ngay'])

    email_subject = "Xác nhận đặt lịch khám tại Bệnh viện {TenBenhVien} - Mã: {MaDatLich}"

    email_template = """
    Kính gửi: {HoTen},

    Cảm ơn Quý khách đã lựa chọn Bệnh viện {TenBenhVien}.
    Chúng tôi xin thông báo đặt lịch khám của Quý khách đã được xác nhận với thông tin chi tiết như sau:

    Thông tin đặt lịch
    - Mã đặt lịch: {MaDatLich}
    - Họ và tên: {HoTen}
    - Ngày: {Ngay}
    - Giờ: {Gio}
    - Bác sĩ: {doctor_name}
    - Phòng khám: {doctor_room}
    - Chi nhánh/Địa chỉ: {ChiNhanh} - {DiaChi}

    Trước khi tới khám
    - Vui lòng có mặt trước ít nhất 30 phút để làm thủ tục tiếp nhận.
    - Mang theo: CMND/CCCD/Hộ chiếu, thẻ BHYT (nếu sử dụng), các kết quả xét nghiệm/phiếu khám trước (nếu có).
    - Nếu lịch khám bao gồm xét nghiệm yêu cầu nhịn ăn hoặc chuẩn bị đặc biệt, chúng tôi sẽ có thông báo riêng - vui lòng tuân thủ để kết quả chính xác.
    - Thanh toán: hỗ trợ tiền mặt, thẻ nội địa/quốc tế, và áp dụng BHYT theo quy định (nếu có).

    Hủy / đổi lịch
    - Nếu Quý khách cần hủy hoặc thay đổi lịch, vui lòng liên hệ trước ít nhất 24 giờ (nếu có thể) để chúng tôi sắp xếp.
    - Đổi / hủy qua: Hotline: {Hotline} - Email: {EmailCSKH} - Zalo/Chat: {ZaloChatLink} - Hoặc truy cập đường dẫn: {LinkDoiHuy}

    Nếu Quý khách cần hỗ trợ thêm, xin vui lòng liên hệ:
    Bệnh viện {TenBenhVien} - Hotline: {Hotline} - Email: {EmailCSKH}
    Thời gian làm việc: {GioLamViec}

    Một lần nữa xin cảm ơn Quý khách. Kính chúc Quý khách sức khỏe và mong được phục vụ!

    Trân trọng,
    Đội ngũ Chăm sóc Khách hàng
    Bệnh viện {TenBenhVien}
    Địa chỉ: {DiaChi} | Website: {Website}
    """

    subject = email_subject.format(**data)
    body = email_template.format(**data)
    return subject, body

def write_cancel_email_v2(data):
    data = data.copy()
    data['Ngay'] = format_date_vn(data['Ngay'])
    data['NgayHuy'] = format_date_vn(data.get('NgayHuy', datetime.now().strftime("%Y-%m-%d")))

    email_subject = "Xác nhận HỦY lịch khám tại Bệnh viện {TenBenhVien} - Mã: {MaDatLich}"

    email_template = """
    Kính gửi: {HoTen},

    Bệnh viện {TenBenhVien} xin xác nhận rằng lịch khám của Quý khách với thông tin sau đã được HỦY:

    Thông tin đặt lịch (đã hủy):
    - Mã đặt lịch: {MaDatLich}
    - Họ và tên: {HoTen}
    - Ngày: {Ngay}
    - Giờ: {Gio}
    - Bác sĩ: {doctor_name}
    - Phòng khám: {doctor_room}
    - Chi nhánh/Địa chỉ: {ChiNhanh} - {DiaChi}

    Thông tin hủy
    - Lý do: {LyDoHuy}
    - Ngày hủy: {NgayHuy}

    Nếu quý khách hủy nhầm hoặc muốn đặt lại lịch, vui lòng liên hệ qua:
    - Hotline: {Hotline}
    - Email: {EmailCSKH}
    - Zalo/Chat: {ZaloChatLink}
    - Hoặc truy cập đường dẫn: {LinkDoiHuy}

    Nếu Quý khách cần hỗ trợ thêm, xin vui lòng liên hệ:
    Bệnh viện {TenBenhVien} - Hotline: {Hotline} - Email: {EmailCSKH}
    Thời gian làm việc: {GioLamViec}

    Một lần nữa xin cảm ơn Quý khách. Kính chúc Quý khách sức khỏe và mong được phục vụ!

    Trân trọng,
    Đội ngũ Chăm sóc Khách hàng
    Bệnh viện {TenBenhVien}
    Địa chỉ: {DiaChi} | Website: {Website}
    """

    subject = email_subject.format(**data)
    body = email_template.format(**data)
    return subject, body
