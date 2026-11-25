"""Cloudflare Python Worker backend for Class Merit Hub."""
from __future__ import annotations
import base64, hmac, io, json, re, secrets, time, traceback, zipfile, unicodedata
from xml.sax.saxutils import escape
from urllib.parse import urlparse
from js import Headers, Object, Response as JSResponse, Uint8Array, crypto, console
from pyodide.ffi import to_js
from workers import WorkerEntrypoint

SESSION_COOKIE = "cmh_session"
SESSION_TTL = 28800
# Cloudflare Workers Web Crypto currently rejects PBKDF2 iteration counts above 100,000.
PBKDF2_ITERATIONS = 100000
ROLE_LABELS = {"founder":"Người sáng lập","teacher":"Giáo viên chủ nhiệm","leader":"Tổ trưởng","member":"Thành viên"}

# Danh sách lớp 12A1 lấy từ file Word người dùng cung cấp.
# Tổ 3 không có tên ở STT 7 trong tài liệu nên không tự bổ sung tên.
CLASS_ROSTER = {
    1: ["Thành Danh", "Ánh Dương", "Quỳnh Hương", "Hoàng Khang", "Quốc Kiên", "Bảo Ngọc", "Khánh Ngọc", "Phương Quỳnh", "Thanh Toàn", "Huyền Trân", "Đức Triết", "Long Vũ"],
    2: ["Hồng Hưng", "Minh Đăng", "Tâm Đoan", "Trần Hoàng", "Gia Huy", "Khánh Nam", "Cẩm Phú", "Quang Phúc", "Thuận Thảo", "Gia Thịnh", "Văn Tự", "Đỗ Uyên"],
    3: ["Kiều Diễm", "Thành Đạt", "Hoàng Hải", "Trần B. Hân", "Huy Hiền", "Minh Hoàng", "Nhật Khánh", "Vĩ Lâm", "Uyên Nhi", "Anh Tuấn", "Tấn Tùng"],
    4: ["Anh Duy", "Lê Hân", "Lê Ngọc Hân", "Ng. Trần Hân", "Chánh Huy", "Đình Khải", "Minh Khải", "Thiện Khoa", "Quốc Lâm", "Hồng Thịnh", "Quế Trâm", "Hà Việt"],
}

def _obj(**values):
    result = Object.new()
    for key, value in values.items():
        setattr(result, key, value)
    return result

def _u8(raw):
    return Uint8Array.new(to_js(list(raw)))

def _bytes_from_buffer(buffer):
    return bytes(int(value) for value in Uint8Array.new(buffer))

def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _unb64(value):
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))

def _response(data, status=200, cookie=None):
    headers = Headers.new()
    headers.set("Content-Type", "application/json; charset=utf-8")
    headers.set("Cache-Control", "no-store")
    headers.set("X-Content-Type-Options", "nosniff")
    headers.set("Referrer-Policy", "same-origin")
    if cookie:
        headers.set("Set-Cookie", cookie)
    return JSResponse.new(json.dumps(data, ensure_ascii=False), _obj(status=status, headers=headers))

def _cookie_value(request, name):
    for item in (request.headers.get("Cookie") or "").split(";"):
        key, sep, value = item.strip().partition("=")
        if sep and key == name:
            return value
    return None

def _normal_phone(value):
    phone = re.sub(r"[\s().-]", "", str(value or ""))
    if not re.fullmatch(r"\+?[0-9]{8,16}", phone):
        raise ValueError("Số điện thoại không hợp lệ.")
    return phone

def _normal_login(value):
    raw = str(value or "").strip()
    numeric = re.sub(r"[\s().-]", "", raw)
    if re.fullmatch(r"\+?[0-9]{8,16}", numeric):
        return _normal_phone(raw)
    username = raw.lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{5,31}", username):
        raise ValueError("Tên đăng nhập không hợp lệ.")
    return username

def _password_valid(password):
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        raise ValueError("Mật khẩu phải có từ 8 đến 128 ký tự.")

def _clean(value, field, minimum, maximum):
    result = str(value or "").strip()
    if not minimum <= len(result) <= maximum:
        raise ValueError(field + " phải có từ " + str(minimum) + " đến " + str(maximum) + " ký tự.")
    return result


def _name_key(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold().replace("đ", "d"))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _roster_entry(value):
    key = _name_key(value)
    if not key:
        return None
    for group_no, names in CLASS_ROSTER.items():
        for official_name in names:
            if _name_key(official_name) == key:
                return group_no, official_name
    return None

async def _pbkdf2(password, salt):
    key = await crypto.subtle.importKey("raw", _u8(password.encode("utf-8")), _obj(name="PBKDF2"), False, to_js(["deriveBits"]))
    params = _obj(name="PBKDF2", salt=_u8(salt), iterations=PBKDF2_ITERATIONS, hash="SHA-256")
    return _bytes_from_buffer(await crypto.subtle.deriveBits(params, key, 256))

async def _hash_password(password):
    _password_valid(password)
    salt = secrets.token_bytes(16)
    digest = await _pbkdf2(password, salt)
    return "pbkdf2_sha256$" + str(PBKDF2_ITERATIONS) + "$" + _b64(salt) + "$" + _b64(digest)

async def _verify_password(password, encoded):
    try:
        scheme, rounds, salt_text, digest_text = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256" or int(rounds) != PBKDF2_ITERATIONS:
            return False
        actual = await _pbkdf2(password, _unb64(salt_text))
        return hmac.compare_digest(actual, _unb64(digest_text))
    except Exception:
        return False

async def _sign(payload, secret):
    key = await crypto.subtle.importKey("raw", _u8(secret.encode("utf-8")), _obj(name="HMAC", hash="SHA-256"), False, to_js(["sign"]))
    return _bytes_from_buffer(await crypto.subtle.sign("HMAC", key, _u8(payload)))

async def _verify_signature(payload, signature, secret):
    key = await crypto.subtle.importKey("raw", _u8(secret.encode("utf-8")), _obj(name="HMAC", hash="SHA-256"), False, to_js(["verify"]))
    return bool(await crypto.subtle.verify("HMAC", key, _u8(signature), _u8(payload)))

async def _first(database, sql, *params):
    statement = database.prepare(sql)
    if params:
        statement = statement.bind(*params)
    value = await statement.first()
    return value

async def _all(database, sql, *params):
    statement = database.prepare(sql)
    if params:
        statement = statement.bind(*params)
    result = await statement.all()
    return result["results"]

async def _run(database, sql, *params):
    statement = database.prepare(sql)
    if params:
        statement = statement.bind(*params)
    return await statement.run()

def _public_user(user):
    return {"id":user["id"],"full_name":user["full_name"],"phone":user["phone"],"role":user["role"],"role_label":ROLE_LABELS.get(user["role"],user["role"]),"group_no":user.get("group_no"),"registration_status":user["registration_status"],"is_active":bool(user["is_active"]),"created_at":user["created_at"]}

async def _audit(database, actor_id, action, target_id=None, details=""):
    await _run(database,"INSERT INTO audit_logs(actor_id,action,target_user_id,details) VALUES(?,?,?,?)",actor_id,action,target_id,details[:500])


def _xlsx_text(value):
    raw = str(value if value is not None else "")
    clean = "".join(
        char for char in raw
        if char in "\t\n\r" or (ord(char) >= 32 and not 0xD800 <= ord(char) <= 0xDFFF)
    )
    return escape(clean)

def _xlsx_column(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result

def _xlsx_cell(reference, value, style=None):
    style_attr = ' s="' + str(style) + '"' if style is not None else ""
    if value is None:
        return '<c r="' + reference + '"' + style_attr + '/>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = format(value, ".15g") if isinstance(value, float) else str(value)
        return '<c r="' + reference + '" t="n"' + style_attr + '><v>' + number + '</v></c>'
    return '<c r="' + reference + '" t="inlineStr"' + style_attr + '><is><t xml:space="preserve">' + _xlsx_text(value) + '</t></is></c>'

def _xlsx_sheet_xml(headers, rows, widths):
    last_column = _xlsx_column(len(headers))
    last_row = len(rows) + 1
    xml_rows = []
    all_rows = [headers] + rows
    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cells.append(_xlsx_cell(_xlsx_column(column_index) + str(row_index), value, 1 if row_index == 1 else None))
        height = ' ht="25" customHeight="1"' if row_index == 1 else ""
        xml_rows.append('<row r="' + str(row_index) + '"' + height + '>' + "".join(cells) + '</row>')
    columns = []
    for index, width in enumerate(widths, start=1):
        columns.append('<col min="' + str(index) + '" max="' + str(index) + '" width="' + str(width) + '" customWidth="1"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="19"/>'
        '<cols>' + "".join(columns) + '</cols>'
        '<sheetData>' + "".join(xml_rows) + '</sheetData>'
        '<autoFilter ref="A1:' + last_column + str(last_row) + '"/>'
        '<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
        '</worksheet>'
    )

def _build_xlsx(sheets):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join('<Override PartName="/xl/worksheets/sheet' + str(index) + '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for index in range(1, len(sheets) + 1))
            + '</Types>'
        )
        archive.writestr("_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        )
        workbook_sheets = "".join(
            '<sheet name="' + _xlsx_text(sheet[0]) + '" sheetId="' + str(index) + '" r:id="rId' + str(index) + '"/>'
            for index, sheet in enumerate(sheets, start=1)
        )
        archive.writestr("xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="12000"/></bookViews>'
            '<sheets>' + workbook_sheets + '</sheets></workbook>'
        )
        archive.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join('<Relationship Id="rId' + str(index) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' + str(index) + '.xml"/>' for index in range(1, len(sheets) + 1))
            + '<Relationship Id="rId' + str(len(sheets) + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )
        archive.writestr("xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF24578F"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFE3EAF3"/></left><right style="thin"><color rgb="FFE3EAF3"/></right><top style="thin"><color rgb="FFE3EAF3"/></top><bottom style="thin"><color rgb="FFE3EAF3"/></bottom><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr("xl/worksheets/sheet" + str(index) + ".xml", _xlsx_sheet_xml(sheet[1], sheet[2], sheet[3]))
    return output.getvalue()

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path
        if path.startswith("/api/"):
            try:
                return await self._api(request, path)
            except ValueError as exc:
                return _response({"error":str(exc)},400)
            except Exception as exc:
                console.error("Class Merit Hub API error", path, repr(exc), traceback.format_exc())
                return _response({"error":"Đã xảy ra lỗi máy chủ. Vui lòng thử lại."},500)
        return await self.env.ASSETS.fetch(request)

    async def _json_body(self, request):
        try:
            body = await request.json()
        except Exception as exc:
            raise ValueError("Dữ liệu gửi lên không phải JSON hợp lệ.") from exc
        if not isinstance(body,dict):
            raise ValueError("Dữ liệu gửi lên không hợp lệ.")
        return body

    def _check_origin(self, request):
        origin = request.headers.get("Origin")
        if origin:
            parsed=urlparse(request.url)
            expected=parsed.scheme+"://"+parsed.netloc
            if origin.rstrip("/") != expected.rstrip("/"):
                raise ValueError("Yêu cầu không cùng nguồn gốc.")

    def _cookie(self, token=None):
        if token:
            return SESSION_COOKIE+"="+token+"; Path=/; Max-Age="+str(SESSION_TTL)+"; HttpOnly; Secure; SameSite=Lax"
        return SESSION_COOKIE+"=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"

    async def _new_session(self,user):
        secret=getattr(self.env,"SESSION_SECRET","") or ""
        if len(secret)<32:
            raise ValueError("Quản trị viên chưa cấu hình SESSION_SECRET (tối thiểu 32 ký tự).")
        now=int(time.time())
        payload=json.dumps({"uid":int(user["id"]),"sv":int(user["session_version"]),"exp":now+SESSION_TTL},separators=(",",":")).encode()
        return _b64(payload)+"."+_b64(await _sign(payload,secret))

    async def _actor(self,request,database):
        token=_cookie_value(request,SESSION_COOKIE)
        secret=getattr(self.env,"SESSION_SECRET","") or ""
        if not token or len(secret)<32:
            return None
        try:
            payload_text,signature_text=token.split(".",1)
            payload=_unb64(payload_text)
            if not await _verify_signature(payload,_unb64(signature_text),secret):
                return None
            session=json.loads(payload.decode())
            if int(session.get("exp",0))<int(time.time()):
                return None
            user=await _first(database,"SELECT id,full_name,phone,password_hash,role,group_no,is_active,registration_status,session_version,created_at FROM users WHERE id=?",int(session["uid"]))
            if not user or not user["is_active"] or user["registration_status"]!="approved" or int(user["session_version"])!=int(session["sv"]):
                return None
            return user
        except Exception:
            return None

    async def _member_allowed(self,actor,member_id):
        member=await _first(self.env.DB,"SELECT id,full_name,phone,role,group_no,is_active,registration_status,created_at FROM users WHERE id=?",member_id)
        if not member or member["role"]!="member" or not member["is_active"] or member["registration_status"]!="approved":
            raise ValueError("Không tìm thấy thành viên đang hoạt động.")
        if actor["role"] in ("founder","teacher"):
            return member
        if actor["role"]=="leader" and int(actor["group_no"])==int(member["group_no"]):
            return member
        if actor["role"]=="member" and int(actor["id"])==int(member["id"]):
            return member
        raise ValueError("Bạn không có quyền xem dữ liệu thành viên này.")

    async def _member_records(self,member_id):
        member=await _first(self.env.DB,"SELECT id,full_name,phone,role,group_no,is_active,registration_status,created_at FROM users WHERE id=?",member_id)
        if not member or member["role"]!="member":
            raise ValueError("Không tìm thấy thành viên.")
        scores=await _all(self.env.DB,"SELECT id,points,category,note,created_at FROM score_entries WHERE member_id=? AND is_deleted=0 ORDER BY created_at DESC,id DESC LIMIT 100",member_id)
        evaluations=await _all(self.env.DB,"SELECT id,content,created_at FROM evaluations WHERE member_id=? AND is_deleted=0 ORDER BY created_at DESC,id DESC LIMIT 100",member_id)
        return {"member":{"id":member["id"],"full_name":member["full_name"],"phone":member["phone"],"group_no":member["group_no"]},"total_points":sum(float(x["points"]) for x in scores),"scores":scores,"evaluations":evaluations}

    async def _dashboard(self,actor):
        database=self.env.DB
        if actor["role"]=="member":
            return {"user":_public_user(actor),"personal":await self._member_records(int(actor["id"]))}

        groups=[int(actor["group_no"])] if actor["role"]=="leader" else [1,2,3,4]
        assignment_rows=await _all(database,"SELECT student_key,group_no FROM roster_assignments")
        roster_group_overrides={str(row["student_key"]):int(row["group_no"]) for row in assignment_rows}
        all_roster_keys={_name_key(name) for names in CLASS_ROSTER.values() for name in names}

        rows=await _all(database,
            "SELECT u.id,u.full_name,u.phone,u.role,u.group_no,u.is_active,u.registration_status,u.created_at,"
            "COALESCE((SELECT SUM(s.points) FROM score_entries s WHERE s.member_id=u.id AND s.is_deleted=0),0) AS total_points "
            "FROM users u WHERE u.role IN ('member','leader') ORDER BY u.created_at DESC,u.id DESC"
        )
        matched={}
        extras=[]
        for row in rows:
            key=_name_key(row["full_name"])
            if key in all_roster_keys:
                priority=0 if row["is_active"] and row["registration_status"]=="approved" else 1 if row["is_active"] and row["registration_status"]=="pending" else 2
                current=matched.get(key)
                current_priority=99 if current is None else (0 if current["is_active"] and current["registration_status"]=="approved" else 1 if current["is_active"] and current["registration_status"]=="pending" else 2)
                if current is None or priority<current_priority:
                    matched[key]=row
            elif row["role"]=="member" and row["is_active"] and row["registration_status"]=="approved":
                extras.append(row)

        group_data=[]
        for group_no in groups:
            roster_names=[]
            for original_group,names in CLASS_ROSTER.items():
                for official_name in names:
                    key=_name_key(official_name)
                    row=matched.get(key)
                    effective_group=int(row["group_no"]) if row else int(roster_group_overrides.get(key,original_group))
                    if effective_group==group_no:
                        roster_names.append(official_name)

            members=[]
            for official_name in roster_names:
                row=matched.get(_name_key(official_name))
                if row and row["role"]=="leader":
                    continue
                if row and row["is_active"] and row["registration_status"]=="approved":
                    members.append({
                        "id":row["id"],"full_name":official_name,"phone":row["phone"],
                        "total_points":float(row["total_points"] or 0),"status_label":"Đang hoạt động"
                    })
                elif row and row["is_active"] and row["registration_status"]=="pending":
                    members.append({
                        "id":None,"full_name":official_name,"phone":"",
                        "total_points":0,"status_label":"Đang chờ duyệt"
                    })
                elif row and row["registration_status"]=="rejected":
                    members.append({
                        "id":None,"full_name":official_name,"phone":"",
                        "total_points":0,"status_label":"Đăng ký đã bị từ chối"
                    })
                elif row and not row["is_active"]:
                    members.append({
                        "id":None,"full_name":official_name,"phone":"",
                        "total_points":0,"status_label":"Tài khoản đã bị khóa"
                    })
                else:
                    members.append({
                        "id":None,"full_name":official_name,"phone":"",
                        "total_points":0,"status_label":"Chưa kích hoạt tài khoản"
                    })

            for row in extras:
                if int(row["group_no"])==group_no:
                    members.append({
                        "id":row["id"],"full_name":row["full_name"],"phone":row["phone"],
                        "total_points":float(row["total_points"] or 0),"status_label":"Đang hoạt động"
                    })

            leader=await _first(database,
                "SELECT id,full_name FROM users WHERE role='leader' AND group_no=? AND is_active=1 AND registration_status='approved' LIMIT 1",
                group_no
            )
            group_data.append({
                "group_no":group_no,
                "leader":{"id":leader["id"],"full_name":leader["full_name"]} if leader else None,
                "member_count":len(members)+(1 if leader else 0),
                "active_count":sum(1 for member in members if member["id"] is not None)+(1 if leader else 0),
                "total_points":sum(float(member["total_points"]) for member in members),
                "members":members
            })
        pending=[]
        if actor["role"] in ("founder","teacher"):
            pending=await _all(database,"SELECT id,full_name,phone,group_no,created_at FROM users WHERE role='member' AND registration_status='pending' ORDER BY created_at ASC")
        return {"user":_public_user(actor),"groups":group_data,"pending_members":pending}

    async def _export_merit_excel(self, actor):
        database = self.env.DB
        members = await _all(database,
            "SELECT u.id,u.group_no,u.full_name,u.phone,u.is_active,u.created_at,"
            "COALESCE(s.total_points,0) AS total_points,COALESCE(s.score_count,0) AS score_count,"
            "COALESCE(s.positive_points,0) AS positive_points,COALESCE(s.negative_points,0) AS negative_points,"
            "COALESCE(e.evaluation_count,0) AS evaluation_count "
            "FROM users u "
            "LEFT JOIN (SELECT member_id,SUM(points) AS total_points,COUNT(*) AS score_count,"
            "SUM(CASE WHEN points>0 THEN points ELSE 0 END) AS positive_points,"
            "SUM(CASE WHEN points<0 THEN points ELSE 0 END) AS negative_points "
            "FROM score_entries WHERE is_deleted=0 GROUP BY member_id) s ON s.member_id=u.id "
            "LEFT JOIN (SELECT member_id,COUNT(*) AS evaluation_count FROM evaluations WHERE is_deleted=0 GROUP BY member_id) e ON e.member_id=u.id "
            "WHERE u.role='member' AND u.registration_status='approved' "
            "ORDER BY u.group_no,u.full_name COLLATE NOCASE"
        )
        score_rows = await _all(database,
            "SELECT u.group_no,u.full_name,u.phone,s.points,s.category,s.note,"
            "COALESCE(c.full_name,'Không rõ') AS creator_name,s.created_at "
            "FROM score_entries s JOIN users u ON u.id=s.member_id "
            "LEFT JOIN users c ON c.id=s.created_by "
            "WHERE s.is_deleted=0 AND u.role='member' AND u.registration_status='approved' "
            "ORDER BY u.group_no,u.full_name COLLATE NOCASE,s.created_at,s.id"
        )
        evaluation_rows = await _all(database,
            "SELECT u.group_no,u.full_name,u.phone,e.content,"
            "COALESCE(c.full_name,'Không rõ') AS evaluator_name,e.created_at "
            "FROM evaluations e JOIN users u ON u.id=e.member_id "
            "LEFT JOIN users c ON c.id=e.evaluator_id "
            "WHERE e.is_deleted=0 AND u.role='member' AND u.registration_status='approved' "
            "ORDER BY u.group_no,u.full_name COLLATE NOCASE,e.created_at,e.id"
        )
        summary_data = []
        for member in members:
            summary_data.append([
                "Tổ " + str(member["group_no"]),
                member["full_name"],
                member["phone"],
                "Đang hoạt động" if int(member["is_active"]) else "Đã khóa",
                float(member["total_points"] or 0),
                int(member["score_count"] or 0),
                float(member["positive_points"] or 0),
                float(member["negative_points"] or 0),
                int(member["evaluation_count"] or 0),
                member["created_at"],
            ])
        score_data = [[
            "Tổ " + str(row["group_no"]),row["full_name"],row["phone"],
            float(row["points"]),row["category"],row["note"],row["creator_name"],row["created_at"]
        ] for row in score_rows]
        evaluation_data = [[
            "Tổ " + str(row["group_no"]),row["full_name"],row["phone"],
            row["content"],row["evaluator_name"],row["created_at"]
        ] for row in evaluation_rows]
        sheets = [
            ("Tổng hợp",["Tổ","Họ và tên","Tên đăng nhập / SĐT","Trạng thái","Tổng điểm","Số lần ghi điểm","Điểm cộng","Điểm trừ","Số nhận xét","Ngày tạo tài khoản"],summary_data,[9,26,17,17,13,16,14,14,14,21]),
            ("Lịch sử điểm",["Tổ","Họ và tên","Tên đăng nhập / SĐT","Điểm (+/-)","Loại điểm","Lý do / minh chứng","Người ghi điểm","Thời gian"],score_data,[9,25,17,13,18,50,24,21]),
            ("Nhận xét",["Tổ","Họ và tên","Tên đăng nhập / SĐT","Nội dung nhận xét","Người nhận xét","Thời gian"],evaluation_data,[9,25,17,55,24,21]),
        ]
        workbook = _build_xlsx(sheets)
        await _audit(database,int(actor["id"]),"export_merit_excel",None,
            "Xuất Excel: " + str(len(members)) + " thành viên, " + str(len(score_rows)) + " lượt ghi điểm, " + str(len(evaluation_rows)) + " nhận xét."
        )
        headers = Headers.new()
        headers.set("Content-Type","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        headers.set("Content-Disposition",'attachment; filename="diem-thi-dua-lop-' + time.strftime("%Y%m%d-%H%M%S",time.gmtime()) + '.xlsx"')
        headers.set("Cache-Control","no-store")
        headers.set("X-Content-Type-Options","nosniff")
        headers.set("Referrer-Policy","same-origin")
        return JSResponse.new(_u8(workbook),_obj(status=200,headers=headers))

    async def _api(self,request,path):
        method=request.method.upper()
        database=self.env.DB
        if path=="/api/healthz" and method=="GET":
            await _first(database,"SELECT 1 AS ok")
            return _response({"status":"ok"})
        if path=="/api/bootstrap/status" and method=="GET":
            founder=await _first(database,"SELECT id FROM users WHERE role='founder' LIMIT 1")
            return _response({"founder_exists":bool(founder),"setup_token_configured":bool(getattr(self.env,"FOUNDER_SETUP_TOKEN","") or "")})
        if method in ("POST","PUT","DELETE"):
            self._check_origin(request)

        if path=="/api/bootstrap" and method=="POST":
            body=await self._json_body(request)
            expected=getattr(self.env,"FOUNDER_SETUP_TOKEN","") or ""
            if len(expected)<24 or not hmac.compare_digest(expected,str(body.get("setup_token",""))):
                return _response({"error":"Mã thiết lập không đúng hoặc chưa được cấu hình."},403)
            if await _first(database,"SELECT id FROM users WHERE role='founder' LIMIT 1"):
                return _response({"error":"Tài khoản người sáng lập đã được thiết lập."},409)
            name=_clean(body.get("full_name"),"Họ và tên",2,100)
            phone=_normal_phone(body.get("phone"))
            password_hash=await _hash_password(str(body.get("password") or ""))
            await _run(database,"INSERT INTO users(full_name,phone,password_hash,role,group_no,is_active,registration_status) VALUES(?,?,?,'founder',NULL,1,'approved')",name,phone,password_hash)
            user=await _first(database,"SELECT * FROM users WHERE phone=?",phone)
            await _audit(database,int(user["id"]),"founder_bootstrap",int(user["id"]))
            return _response({"ok":True,"user":_public_user(user)},201,self._cookie(await self._new_session(user)))

        if path=="/api/register" and method=="POST":
            body=await self._json_body(request)
            name=_clean(body.get("full_name"),"Họ và tên",2,100)
            roster_member=_roster_entry(name)
            if roster_member:
                default_group,name=roster_member
                assignment=await _first(database,"SELECT group_no FROM roster_assignments WHERE student_key=?",_name_key(name))
                group_no=int(assignment["group_no"]) if assignment else int(default_group)
            else:
                group_no=int(body.get("group_no",0))
                if group_no not in (1,2,3,4):
                    raise ValueError("Vui lòng chọn tổ từ 1 đến 4.")
            phone=_normal_phone(body.get("phone"))
            password_hash=await _hash_password(str(body.get("password") or ""))
            try:
                await _run(database,"INSERT INTO users(full_name,phone,password_hash,role,group_no,is_active,registration_status) VALUES(?,?,?,'member',?,1,'pending')",name,phone,password_hash,group_no)
            except Exception as exc:
                raise ValueError("Số điện thoại đã được đăng ký hoặc không hợp lệ.") from exc
            registered=await _first(database,"SELECT id FROM users WHERE phone=?",phone)
            if registered:
                await _audit(database,None,"member_registration",int(registered["id"]),name+" | "+phone+" | Tổ "+str(group_no))
            return _response({"ok":True,"message":"Đã gửi đăng ký. Người sáng lập sẽ nhận được thông báo trong Class Merit Hub; vui lòng chờ duyệt."},201)

        if path=="/api/login" and method=="POST":
            body=await self._json_body(request)
            phone=_normal_login(body.get("phone") or body.get("username"))
            password=str(body.get("password") or "")
            throttle=await _first(database,"SELECT failed_count,locked_until FROM login_throttle WHERE username_key=?",phone)
            now=int(time.time())
            if throttle and int(throttle["locked_until"])>now:
                return _response({"error":"Tài khoản tạm khóa do đăng nhập sai nhiều lần. Hãy thử lại sau 15 phút."},423)
            user=await _first(database,"SELECT id,full_name,phone,password_hash,role,group_no,is_active,registration_status,session_version,created_at FROM users WHERE phone=?",phone)
            valid=bool(user and user["is_active"] and user["registration_status"]=="approved")
            if valid:
                valid=await _verify_password(password,user["password_hash"])
            if not valid:
                count=int(throttle["failed_count"])+1 if throttle else 1
                locked=now+900 if count>=5 else 0
                await _run(database,"INSERT INTO login_throttle(username_key,failed_count,locked_until,updated_at) VALUES(?,?,?,?) ON CONFLICT(username_key) DO UPDATE SET failed_count=excluded.failed_count,locked_until=excluded.locked_until,updated_at=excluded.updated_at",phone,count,locked,now)
                return _response({"error":"Thông tin đăng nhập không đúng hoặc tài khoản chưa được duyệt."},401)
            await _run(database,"DELETE FROM login_throttle WHERE username_key=?",phone)
            return _response({"ok":True,"user":_public_user(user)},200,self._cookie(await self._new_session(user)))

        if path=="/api/logout" and method=="POST":
            return _response({"ok":True},200,self._cookie())

        actor=await self._actor(request,database)
        if not actor:
            return _response({"error":"Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."},401)
        if path=="/api/me" and method=="GET":
            return _response({"user":_public_user(actor)})
        if path=="/api/dashboard" and method=="GET":
            return _response(await self._dashboard(actor))

        if path=="/api/class/assign-leader" and method=="POST":
            if actor["role"] not in ("founder","teacher"):
                return _response({"error":"Chỉ Người sáng lập và Giáo viên chủ nhiệm được phân công Tổ trưởng."},403)
            body=await self._json_body(request)
            group_no=int(body.get("group_no") or 0)
            member_id=int(body.get("member_id") or 0)
            if group_no not in (1,2,3,4) or member_id<=0:
                raise ValueError("Vui lòng chọn tổ và thành viên hợp lệ.")
            target=await _first(database,
                "SELECT id,full_name,role,group_no,is_active,registration_status FROM users WHERE id=?",
                member_id
            )
            if not target or target["role"] not in ("member","leader") or not target["is_active"] or target["registration_status"]!="approved":
                raise ValueError("Chỉ có thể bổ nhiệm học sinh có tài khoản đang hoạt động và đã được duyệt.")
            if int(target["group_no"])!=group_no:
                raise ValueError("Học sinh hiện thuộc Tổ "+str(target["group_no"])+". Hãy chuyển học sinh sang đúng tổ trước khi bổ nhiệm.")
            current=await _first(database,
                "SELECT id,full_name FROM users WHERE role='leader' AND group_no=? AND is_active=1 LIMIT 1",
                group_no
            )
            if current and int(current["id"])==member_id:
                return _response({"ok":True,"message":target["full_name"]+" hiện đã là Tổ trưởng Tổ "+str(group_no)+"."})
            if target["role"]=="leader":
                raise ValueError("Học sinh này đang là Tổ trưởng của tổ khác. Hãy điều chỉnh phân công hiện tại trước.")

            old_leader=None
            if current:
                old_leader=await _first(database,"SELECT id,full_name FROM users WHERE id=? AND role='leader'",int(current["id"]))
                if old_leader:
                    await _run(database,"UPDATE users SET role='member' WHERE id=? AND role='leader'",int(old_leader["id"]))
            try:
                await _run(database,
                    "UPDATE users SET role='leader' WHERE id=? AND role='member' AND group_no=? AND is_active=1 AND registration_status='approved'",
                    member_id,group_no
                )
                promoted=await _first(database,"SELECT id FROM users WHERE id=? AND role='leader'",member_id)
                if not promoted:
                    raise ValueError("Không thể cập nhật vai trò Tổ trưởng. Hãy tải lại trang và thử lại.")
            except Exception:
                if old_leader:
                    try:
                        await _run(database,"UPDATE users SET role='leader' WHERE id=? AND role='member' AND group_no=? AND is_active=1",
                            int(old_leader["id"]),group_no)
                    except Exception:
                        pass
                raise
            if old_leader:
                await _audit(database,int(actor["id"]),"demote_group_leader",int(old_leader["id"]),
                    old_leader["full_name"]+" được chuyển từ Tổ trưởng thành Thành viên Tổ "+str(group_no))
            await _audit(database,int(actor["id"]),"assign_group_leader",member_id,
                target["full_name"]+" được bổ nhiệm làm Tổ trưởng Tổ "+str(group_no))
            return _response({"ok":True,"message":"Đã cập nhật Tổ trưởng Tổ "+str(group_no)+"."})

        if path=="/api/class/transfer-member" and method=="POST":
            if actor["role"] not in ("founder","teacher"):
                return _response({"error":"Chỉ Người sáng lập và Giáo viên chủ nhiệm được chuyển thành viên giữa các tổ."},403)
            body=await self._json_body(request)
            target_group=int(body.get("to_group") or 0)
            if target_group not in (1,2,3,4):
                raise ValueError("Tổ đích phải nằm trong khoảng 1 đến 4.")

            member=None
            roster=None
            if body.get("member_id"):
                member_id=int(body.get("member_id") or 0)
                member=await _first(database,
                    "SELECT id,full_name,role,group_no,is_active,registration_status FROM users WHERE id=?",
                    member_id
                )
                if not member or member["role"] not in ("member","leader"):
                    raise ValueError("Không tìm thấy tài khoản học sinh hợp lệ.")
                roster=_roster_entry(member["full_name"])
            else:
                roster=_roster_entry(body.get("full_name"))
                if not roster:
                    raise ValueError("Chỉ có thể chuyển tên học sinh có trong danh sách lớp. Với học sinh khác, hãy chọn tài khoản cụ thể.")
                original_group,official_name=roster
                matches=await _all(database,
                    "SELECT id,full_name,role,group_no,is_active,registration_status FROM users WHERE role IN ('member','leader')"
                )
                same_name=[row for row in matches if _name_key(row["full_name"])==_name_key(official_name)]
                if len(same_name)>1:
                    raise ValueError("Có nhiều tài khoản trùng tên "+official_name+". Hãy chọn tài khoản cụ thể trong danh sách.")
                member=same_name[0] if same_name else None

            if roster:
                original_group,official_name=roster
                full_name=official_name
            else:
                full_name=member["full_name"]
                original_group=int(member["group_no"])

            if member:
                current_group=int(member["group_no"])
            else:
                override=await _first(database,"SELECT group_no FROM roster_assignments WHERE student_key=?",_name_key(full_name))
                current_group=int(override["group_no"]) if override else int(original_group)

            if current_group==target_group:
                return _response({"ok":True,"message":full_name+" hiện đã thuộc Tổ "+str(target_group)+"."})

            demoted_leader=bool(member and member["role"]=="leader")
            if member:
                if demoted_leader:
                    await _run(database,"UPDATE users SET role='member',group_no=? WHERE id=?",target_group,int(member["id"]))
                else:
                    await _run(database,"UPDATE users SET group_no=? WHERE id=?",target_group,int(member["id"]))

            if roster:
                if target_group==int(original_group):
                    await _run(database,"DELETE FROM roster_assignments WHERE student_key=?",_name_key(full_name))
                else:
                    await _run(database,
                        "INSERT INTO roster_assignments(student_key,full_name,group_no,updated_by,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) "
                        "ON CONFLICT(student_key) DO UPDATE SET full_name=excluded.full_name,group_no=excluded.group_no,updated_by=excluded.updated_by,updated_at=CURRENT_TIMESTAMP",
                        _name_key(full_name),full_name,target_group,int(actor["id"])
                    )

            await _audit(database,int(actor["id"]),"transfer_member_group",int(member["id"]) if member else None,
                full_name+" | Tổ "+str(current_group)+" → Tổ "+str(target_group)+
                (" | Tổ trưởng cũ được chuyển thành Thành viên" if demoted_leader else ""))
            return _response({"ok":True,"message":"Đã chuyển "+full_name+" từ Tổ "+str(current_group)+" sang Tổ "+str(target_group)+"."})

        if path=="/api/accounts/bulk-create-roster" and method=="POST":
            if actor["role"] != "founder":
                return _response({"error":"Chỉ Người sáng lập được tạo tài khoản đồng loạt cho lớp."},403)
            body=await self._json_body(request)
            group_no=int(body.get("group_no") or 0)
            if group_no not in (1,2,3,4):
                raise ValueError("Vui lòng chọn tổ từ 1 đến 4.")

            existing_rows=await _all(database,
                "SELECT id,full_name,phone,group_no,is_active,registration_status FROM users WHERE role='member'"
            )
            target_keys={_name_key(name) for name in CLASS_ROSTER[group_no]}
            existing_by_name={}
            for row in existing_rows:
                key=_name_key(row["full_name"])
                if key not in target_keys:
                    continue
                current=existing_by_name.get(key)
                priority=0 if row["is_active"] and row["registration_status"]=="approved" else 1 if row["is_active"] and row["registration_status"]=="pending" else 2
                current_priority=99 if current is None else (0 if current["is_active"] and current["registration_status"]=="approved" else 1 if current["is_active"] and current["registration_status"]=="pending" else 2)
                if current is None or priority<current_priority:
                    existing_by_name[key]=row

            entries=[]
            pending_creations=[]
            created_count=0
            existing_count=0
            for index,official_name in enumerate(CLASS_ROSTER[group_no],start=1):
                key=_name_key(official_name)
                assignment=await _first(database,"SELECT group_no FROM roster_assignments WHERE student_key=?",key)
                assigned_group=int(assignment["group_no"]) if assignment else group_no
                existing=existing_by_name.get(key)
                if existing:
                    if int(existing["group_no"]) != assigned_group:
                        await _run(database,"UPDATE users SET group_no=? WHERE id=?",assigned_group,int(existing["id"]))
                        await _audit(database,int(actor["id"]),"roster_group_corrected",int(existing["id"]),
                            official_name+" | chuyển về Tổ "+str(group_no))
                    if not existing["is_active"]:
                        status="Tài khoản đã khóa — không cấp lại tự động"
                    elif existing["registration_status"]=="pending":
                        status="Đã có tài khoản chờ duyệt — giữ nguyên mật khẩu"
                    elif existing["registration_status"]=="approved":
                        status="Đã có tài khoản — giữ nguyên mật khẩu"
                    else:
                        status="Đăng ký đã bị từ chối — cần kiểm tra"
                    entries.append({
                        "group_no":assigned_group,"stt":index,"full_name":official_name,
                        "username":existing["phone"],"password":"","status":status
                    })
                    existing_count+=1
                    continue

                username="12a1-t"+str(assigned_group)+"-"+str(index).zfill(2)
                collision=await _first(database,"SELECT id FROM users WHERE phone=?",username)
                if collision:
                    username=username+"-"+secrets.token_hex(2)
                    while await _first(database,"SELECT id FROM users WHERE phone=?",username):
                        username="12a1-t"+str(assigned_group)+"-"+str(index).zfill(2)+"-"+secrets.token_hex(3)
                password=secrets.token_urlsafe(12)
                password_hash=await _hash_password(password)
                pending_creations.append({
                    "group_no":assigned_group,"stt":index,"full_name":official_name,
                    "username":username,"password":password,"password_hash":password_hash
                })

            # Finish password hashing for the whole group before writing any new account.
            # If a hash operation fails, no credentials from this group become orphaned in D1.
            created_ids=[]
            try:
                for item in pending_creations:
                    await _run(database,
                        "INSERT INTO users(full_name,phone,password_hash,role,group_no,is_active,registration_status) VALUES(?,?,?,'member',?,1,'approved')",
                        item["full_name"],item["username"],item["password_hash"],item["group_no"]
                    )
                    created=await _first(database,"SELECT id FROM users WHERE phone=?",item["username"])
                    created_id=int(created["id"])
                    created_ids.append(created_id)
                    await _audit(database,int(actor["id"]),"bulk_create_student_account",created_id,
                        "Tổ "+str(item["group_no"])+" | "+item["full_name"]+" | "+item["username"])
                    entries.append({
                        "group_no":group_no,"stt":item["stt"],"full_name":item["full_name"],
                        "username":item["username"],"password":item["password"],"status":"Tài khoản mới — đã kích hoạt"
                    })
                    created_count+=1
            except Exception:
                for created_id in created_ids:
                    try:
                        await _run(database,"DELETE FROM audit_logs WHERE actor_id=? AND action='bulk_create_student_account' AND target_user_id=?",
                            int(actor["id"]),created_id)
                        await _run(database,"DELETE FROM users WHERE id=?",created_id)
                    except Exception:
                        pass
                raise

            return _response({
                "ok":True,"group_no":group_no,"created_count":created_count,
                "existing_count":existing_count,"entries":entries
            },201)

        if path=="/api/export/merit.xlsx":
            if actor["role"] not in ("founder","teacher"):
                return _response({"error":"Chỉ Người sáng lập và Giáo viên chủ nhiệm được xuất dữ liệu Excel."},403)
            if method != "GET":
                return _response({"error":"Phương thức không được hỗ trợ."},405)
            return await self._export_merit_excel(actor)

        if path=="/api/accounts" and method=="GET":
            if actor["role"]=="member":
                return _response({"accounts":[_public_user(actor)]})
            if actor["role"]=="leader":
                rows=await _all(database,"SELECT * FROM users WHERE role='member' AND group_no=? ORDER BY full_name",int(actor["group_no"]))
            else:
                rows=await _all(database,"SELECT * FROM users ORDER BY role,group_no,full_name")
            return _response({"accounts":[_public_user(row) for row in rows]})

        if path=="/api/accounts" and method=="POST":
            body=await self._json_body(request)
            role=str(body.get("role") or "member")
            group_no=body.get("group_no")
            if role not in ("teacher","leader","member"):
                raise ValueError("Vai trò không hợp lệ.")
            if actor["role"]=="leader":
                if role!="member":
                    return _response({"error":"Tổ trưởng chỉ được tạo thành viên trong tổ mình."},403)
                group_no=int(actor["group_no"])
            elif actor["role"]=="teacher":
                if role not in ("leader","member"):
                    return _response({"error":"Giáo viên chỉ được tạo Tổ trưởng hoặc Thành viên."},403)
            elif actor["role"]!="founder":
                return _response({"error":"Bạn không có quyền tạo tài khoản."},403)
            name=_clean(body.get("full_name"),"Họ và tên",2,100)
            roster_member=_roster_entry(name) if role=="member" else None
            if roster_member:
                roster_group,name=roster_member
                if actor["role"]=="leader" and int(actor["group_no"])!=roster_group:
                    return _response({"error":"Học sinh này thuộc Tổ "+str(roster_group)+", bạn chỉ được tạo tài khoản cho thành viên tổ mình."},403)
                group_no=roster_group
            if role in ("leader","member"):
                group_no=int(group_no or 0)
                if group_no not in (1,2,3,4):
                    raise ValueError("Vui lòng chọn tổ từ 1 đến 4.")
            else:
                group_no=None
            phone=_normal_phone(body.get("phone"))
            password_hash=await _hash_password(str(body.get("password") or ""))
            try:
                await _run(database,"INSERT INTO users(full_name,phone,password_hash,role,group_no,is_active,registration_status) VALUES(?,?,?,?,?,1,'approved')",name,phone,password_hash,role,group_no)
            except Exception as exc:
                raise ValueError("Số điện thoại trùng hoặc đã tồn tại Tổ trưởng của tổ này.") from exc
            created=await _first(database,"SELECT id FROM users WHERE phone=?",phone)
            await _audit(database,int(actor["id"]),"create_account",int(created["id"]),role)
            return _response({"ok":True},201)

        if path.startswith("/api/accounts/") and method in ("POST","PUT","DELETE"):
            parts=path.strip("/").split("/")
            if len(parts)==3 and method=="DELETE":
                if actor["role"]!="founder":
                    return _response({"error":"Chỉ Người sáng lập được xóa tài khoản."},403)
                target_id=int(parts[2])
                target=await _first(database,"SELECT * FROM users WHERE id=?",target_id)
                if not target:
                    raise ValueError("Không tìm thấy tài khoản.")
                if target["role"]=="founder":
                    return _response({"error":"Không thể xóa tài khoản Người sáng lập."},403)
                if not target["is_active"]:
                    raise ValueError("Tài khoản này đã được xóa trước đó.")
                await _run(database,"UPDATE users SET is_active=0,session_version=session_version+1,registration_status=CASE WHEN registration_status='pending' THEN 'rejected' ELSE registration_status END WHERE id=?",target_id)
                await _audit(database,int(actor["id"]),"delete_account",target_id,target["full_name"]+" | "+ROLE_LABELS.get(target["role"],target["role"]))
                return _response({"ok":True,"message":"Tài khoản đã bị vô hiệu hóa; dữ liệu thi đua được giữ lại."})
            if len(parts)==4:
                target_id=int(parts[2])
                action=parts[3]
                target=await _first(database,"SELECT * FROM users WHERE id=?",target_id)
                if not target:
                    raise ValueError("Không tìm thấy tài khoản.")
                body=await self._json_body(request)
                if action in ("approve","reject"):
                    if actor["role"] not in ("founder","teacher"):
                        return _response({"error":"Bạn không có quyền duyệt tài khoản."},403)
                    if target["role"]!="member" or target["registration_status"]!="pending":
                        raise ValueError("Tài khoản này không ở trạng thái chờ duyệt.")
                    if action=="approve":
                        roster_member=_roster_entry(target["full_name"])
                        if roster_member:
                            group_no,official_name=roster_member
                        else:
                            official_name=target["full_name"]
                            group_no=int(body.get("group_no") or target["group_no"])
                        if group_no not in (1,2,3,4):
                            raise ValueError("Tổ phải nằm trong khoảng 1 đến 4.")
                        await _run(database,"UPDATE users SET full_name=?,group_no=?,registration_status='approved' WHERE id=?",official_name,group_no,target_id)
                    else:
                        await _run(database,"UPDATE users SET registration_status='rejected',is_active=0 WHERE id=?",target_id)
                    await _audit(database,int(actor["id"]),action+"_registration",target_id)
                    return _response({"ok":True})
                if action=="reset-password":
                    if actor["role"] not in ("founder","teacher"):
                        return _response({"error":"Bạn không có quyền đặt lại mật khẩu."},403)
                    if actor["role"]=="teacher" and target["role"] in ("founder","teacher"):
                        return _response({"error":"Giáo viên không được thay đổi tài khoản Người sáng lập hoặc giáo viên khác."},403)
                    generated_password = "new_password" not in body
                    if generated_password:
                        if actor["role"] != "founder":
                            return _response({"error":"Chỉ Người sáng lập được cấp mật khẩu tạm tự động."},403)
                        if target["role"] != "member" or not target["is_active"] or target["registration_status"] != "approved":
                            return _response({"error":"Chỉ có thể cấp mật khẩu tạm cho thành viên đã được duyệt và đang hoạt động."},400)
                        new_password = secrets.token_urlsafe(12)
                    else:
                        new_password = str(body.get("new_password") or "")
                    password_hash=await _hash_password(new_password)
                    await _run(database,"UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?",password_hash,target_id)
                    details = "Đã cấp mật khẩu tạm; mật khẩu cũ và các phiên đăng nhập trước đã bị thu hồi." if generated_password else ""
                    await _audit(database,int(actor["id"]),"reset_password",target_id,details)
                    response = {"ok":True}
                    if generated_password:
                        response["temporary_password"] = new_password
                    return _response(response)
                if action=="deactivate":
                    if actor["role"]!="founder" or target["role"]=="founder":
                        return _response({"error":"Chỉ Người sáng lập được khóa tài khoản khác."},403)
                    await _run(database,"UPDATE users SET is_active=0,session_version=session_version+1 WHERE id=?",target_id)
                    await _audit(database,int(actor["id"]),"deactivate_account",target_id)
                    return _response({"ok":True})

        if path=="/api/password/change" and method=="POST":
            body=await self._json_body(request)
            if not await _verify_password(str(body.get("old_password") or ""),actor["password_hash"]):
                return _response({"error":"Mật khẩu hiện tại không đúng."},400)
            new_hash=await _hash_password(str(body.get("new_password") or ""))
            await _run(database,"UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?",new_hash,int(actor["id"]))
            await _audit(database,int(actor["id"]),"change_password",int(actor["id"]))
            return _response({"ok":True},200,self._cookie())

        if path.startswith("/api/members/"):
            parts=path.strip("/").split("/")
            if len(parts)>=3:
                member_id=int(parts[2])
                await self._member_allowed(actor,member_id)
                if len(parts)==3 and method=="GET":
                    return _response(await self._member_records(member_id))
                if len(parts)==4 and parts[3]=="scores" and method=="POST":
                    if actor["role"] not in ("founder","teacher","leader"):
                        return _response({"error":"Vai trò này không được phép cộng hoặc trừ điểm."},403)
                    body=await self._json_body(request)
                    points=float(body.get("points",0))
                    if points==0 or points < -100 or points > 100:
                        raise ValueError("Điểm phải khác 0 và nằm trong khoảng -100 đến +100.")
                    category=_clean(body.get("category"),"Loại điểm",2,80)
                    note=_clean(body.get("note"),"Lý do/minh chứng",3,500)
                    await _run(database,"INSERT INTO score_entries(member_id,points,category,note,created_by) VALUES(?,?,?,?,?)",member_id,points,category,note,int(actor["id"]))
                    await _audit(database,int(actor["id"]),"add_score",member_id,str(points)+" | "+category)
                    return _response({"ok":True},201)
                if len(parts)==4 and parts[3]=="evaluations" and method=="POST":
                    if actor["role"] not in ("founder","teacher","leader"):
                        return _response({"error":"Vai trò này không được phép viết nhận xét."},403)
                    body=await self._json_body(request)
                    content=_clean(body.get("content"),"Nhận xét",3,1000)
                    await _run(database,"INSERT INTO evaluations(member_id,content,evaluator_id) VALUES(?,?,?)",member_id,content,int(actor["id"]))
                    await _audit(database,int(actor["id"]),"add_evaluation",member_id)
                    return _response({"ok":True},201)

        if path.startswith("/api/scores/") and method=="DELETE":
            score_id=int(path.rsplit("/",1)[1])
            score=await _first(database,"SELECT id,member_id FROM score_entries WHERE id=? AND is_deleted=0",score_id)
            if not score:
                raise ValueError("Không tìm thấy bản ghi điểm.")
            await self._member_allowed(actor,int(score["member_id"]))
            if actor["role"] not in ("founder","teacher","leader"):
                return _response({"error":"Vai trò này không được phép xóa điểm."},403)
            await _run(database,"UPDATE score_entries SET is_deleted=1,deleted_by=?,deleted_at=CURRENT_TIMESTAMP WHERE id=?",int(actor["id"]),score_id)
            await _audit(database,int(actor["id"]),"delete_score",int(score["member_id"]))
            return _response({"ok":True})

        if path.startswith("/api/evaluations/") and method=="DELETE":
            evaluation_id=int(path.rsplit("/",1)[1])
            evaluation=await _first(database,"SELECT id,member_id FROM evaluations WHERE id=? AND is_deleted=0",evaluation_id)
            if not evaluation:
                raise ValueError("Không tìm thấy nhận xét.")
            await self._member_allowed(actor,int(evaluation["member_id"]))
            if actor["role"] not in ("founder","teacher","leader"):
                return _response({"error":"Vai trò này không được phép xóa nhận xét."},403)
            await _run(database,"UPDATE evaluations SET is_deleted=1,deleted_by=?,deleted_at=CURRENT_TIMESTAMP WHERE id=?",int(actor["id"]),evaluation_id)
            await _audit(database,int(actor["id"]),"delete_evaluation",int(evaluation["member_id"]))
            return _response({"ok":True})

        if path=="/api/audit" and method=="DELETE":
            if actor["role"]!="founder":
                return _response({"error":"Chỉ Người sáng lập được xóa nhật ký quản trị."},403)
            count=await _first(database,"SELECT COUNT(*) AS total FROM audit_logs")
            deleted_count=int(count["total"] or 0)
            await _run(database,"DELETE FROM audit_logs")
            await _audit(database,int(actor["id"]),"clear_audit_logs",None,"Đã xóa "+str(deleted_count)+" nhật ký trước đó.")
            return _response({"ok":True,"deleted_count":deleted_count})

        if path.startswith("/api/audit/") and method=="DELETE":
            if actor["role"]!="founder":
                return _response({"error":"Chỉ Người sáng lập được xóa nhật ký quản trị."},403)
            log_id=int(path.rsplit("/",1)[1])
            log=await _first(database,"SELECT id,action,target_user_id FROM audit_logs WHERE id=?",log_id)
            if not log:
                raise ValueError("Không tìm thấy nhật ký.")
            await _run(database,"DELETE FROM audit_logs WHERE id=?",log_id)
            await _audit(database,int(actor["id"]),"delete_audit_log",log.get("target_user_id"),"Đã xóa nhật ký #"+str(log_id)+" ("+str(log["action"])+").")
            return _response({"ok":True})

        if path=="/api/audit" and method=="GET":
            if actor["role"]!="founder":
                return _response({"error":"Chỉ Người sáng lập được xem nhật ký quản trị."},403)
            rows=await _all(database,"SELECT a.id,a.action,a.details,a.created_at,COALESCE(u.full_name,'Hệ thống') AS actor_name FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 100")
            return _response({"logs":rows})
        return _response({"error":"Không tìm thấy API."},404)
