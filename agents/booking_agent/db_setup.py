import sqlite3
from datetime import datetime

DB_NAME = "schedule.db"

def create_tables(conn):
    cur = conn.cursor()

    # Xoá toàn bộ bảng cũ
    cur.executescript("""
    DROP TABLE IF EXISTS doctors;
    DROP TABLE IF EXISTS work_shifts;
    DROP TABLE IF EXISTS shift_exceptions;
    DROP TABLE IF EXISTS appointments;
    """)

    # Bác sĩ
    cur.execute("""
    CREATE TABLE doctors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        room TEXT NOT NULL
    );
    """)

    # Ca làm việc cố định trong tuần
    cur.execute("""
    CREATE TABLE work_shifts (
        id TEXT NOT NULL,                   -- morning / afternoon
        doctor_id TEXT NOT NULL,
        day_of_week TEXT NOT NULL,          -- "0"=Mon ... "6"=Sun
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        PRIMARY KEY (doctor_id, day_of_week, id),
        FOREIGN KEY (doctor_id) REFERENCES doctors(id)
    );
    """)

    # Ngoại lệ (nghỉ đột xuất hoặc tăng ca)
    cur.execute("""
    CREATE TABLE shift_exceptions (
        doctor_id TEXT NOT NULL,
        date TEXT NOT NULL,                 -- YYYY-MM-DD
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        is_available INTEGER NOT NULL,      -- 0 = nghỉ, 1 = tăng ca
        FOREIGN KEY (doctor_id) REFERENCES doctors(id),
        UNIQUE (doctor_id, date, start_time, end_time)
    );
    """)

    # Cuộc hẹn (appointments)
    cur.execute("""
    CREATE TABLE appointments (
        id TEXT PRIMARY KEY,                -- 5 chữ số, vd "00001"
        doctor_id TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        status TEXT NOT NULL,               -- booked / canceled
        created_at TEXT NOT NULL,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id)
    );
    """)

    conn.commit()

if __name__ == "__main__":
    conn = sqlite3.connect(DB_NAME)
    create_tables(conn)
    conn.close()
    print(f"✅ Database '{DB_NAME}' đã được tạo thành công (chưa có dữ liệu)!")