"""Cloudflare Python Worker backend for Class Merit Hub."""
from __future__ import annotations
import base64, hmac, json, re, secrets, time, traceback
from urllib.parse import urlparse
from js import Headers, Object, Response as JSResponse, Uint8Array, crypto, console
from pyodide.ffi import to_js
from workers import WorkerEntrypoint

SESSION_COOKIE = "cmh_session"
SESSION_TTL = 28800
# Cloudflare Workers Web Crypto currently rejects PBKDF2 iteration counts above 100,000.
PBKDF2_ITERATIONS = 100000
ROLE_LABELS = {"founder":"Người sáng lập","teacher":"Giáo viên chủ nhiệm","leader":"Tổ trưởng","member":"Thành viên"}

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

def _password_valid(password):
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        raise ValueError("Mật khẩu phải có từ 8 đến 128 ký tự.")

def _clean(value, field, minimum, maximum):
    result = str(value or "").strip()
    if not minimum <= len(result) <= maximum:
        raise ValueError(field + " phải có từ " + str(minimum) + " đến " + str(maximum) + " ký tự.")
    return result

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
        group_data=[]
        for group_no in groups:
            members=await _all(database,"SELECT u.id,u.full_name,u.phone,COALESCE((SELECT SUM(s.points) FROM score_entries s WHERE s.member_id=u.id AND s.is_deleted=0),0) AS total_points FROM users u WHERE u.role='member' AND u.group_no=? AND u.is_active=1 AND u.registration_status='approved' ORDER BY u.full_name COLLATE NOCASE",group_no)
            group_data.append({"group_no":group_no,"member_count":len(members),"total_points":sum(float(x["total_points"]) for x in members),"members":members})
        pending=[]
        if actor["role"] in ("founder","teacher"):
            pending=await _all(database,"SELECT id,full_name,phone,group_no,created_at FROM users WHERE role='member' AND registration_status='pending' ORDER BY created_at ASC")
        return {"user":_public_user(actor),"groups":group_data,"pending_members":pending}

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
            phone=_normal_phone(body.get("phone"))
            password_hash=await _hash_password(str(body.get("password") or ""))
            group_no=int(body.get("group_no",0))
            if group_no not in (1,2,3,4):
                raise ValueError("Vui lòng chọn tổ từ 1 đến 4.")
            try:
                await _run(database,"INSERT INTO users(full_name,phone,password_hash,role,group_no,is_active,registration_status) VALUES(?,?,?,'member',?,1,'pending')",name,phone,password_hash,group_no)
            except Exception as exc:
                raise ValueError("Số điện thoại đã được đăng ký hoặc không hợp lệ.") from exc
            registered=await _first(database,"SELECT id FROM users WHERE phone=?",phone)
            if registered:
                await _audit(database,int(registered["id"]),"member_registration",int(registered["id"]),name+" | "+phone+" | Tổ "+str(group_no))
            return _response({"ok":True,"message":"Đã gửi đăng ký. Người sáng lập sẽ nhận được thông báo trong Class Merit Hub; vui lòng chờ duyệt."},201)

        if path=="/api/login" and method=="POST":
            body=await self._json_body(request)
            phone=_normal_phone(body.get("phone"))
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
            if role in ("leader","member"):
                group_no=int(group_no or 0)
                if group_no not in (1,2,3,4):
                    raise ValueError("Vui lòng chọn tổ từ 1 đến 4.")
            else:
                group_no=None
            name=_clean(body.get("full_name"),"Họ và tên",2,100)
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
                        group_no=int(body.get("group_no") or target["group_no"])
                        if group_no not in (1,2,3,4):
                            raise ValueError("Tổ phải nằm trong khoảng 1 đến 4.")
                        await _run(database,"UPDATE users SET group_no=?,registration_status='approved' WHERE id=?",group_no,target_id)
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
            if actor["role"] not in ("founder","teacher"):
                return _response({"error":"Vai trò này cần liên hệ Người sáng lập hoặc Giáo viên để đổi mật khẩu."},403)
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
                    if actor["role"]=="member":
                        return _response({"error":"Thành viên không được tự cộng hoặc trừ điểm."},403)
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
                    if actor["role"]=="member":
                        return _response({"error":"Thành viên không được tự viết nhận xét."},403)
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
            if actor["role"]=="member":
                return _response({"error":"Bạn không có quyền xóa điểm."},403)
            await _run(database,"UPDATE score_entries SET is_deleted=1,deleted_by=?,deleted_at=CURRENT_TIMESTAMP WHERE id=?",int(actor["id"]),score_id)
            await _audit(database,int(actor["id"]),"delete_score",int(score["member_id"]))
            return _response({"ok":True})

        if path.startswith("/api/evaluations/") and method=="DELETE":
            evaluation_id=int(path.rsplit("/",1)[1])
            evaluation=await _first(database,"SELECT id,member_id FROM evaluations WHERE id=? AND is_deleted=0",evaluation_id)
            if not evaluation:
                raise ValueError("Không tìm thấy nhận xét.")
            await self._member_allowed(actor,int(evaluation["member_id"]))
            if actor["role"]=="member":
                return _response({"error":"Bạn không có quyền xóa nhận xét."},403)
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
            rows=await _all(database,"SELECT a.id,a.action,a.details,a.created_at,u.full_name AS actor_name FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 100")
            return _response({"logs":rows})
        return _response({"error":"Không tìm thấy API."},404)
