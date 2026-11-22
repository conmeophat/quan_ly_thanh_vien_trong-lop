const app=document.querySelector("#app"),userbar=document.querySelector("#userbar");let me=null,tab="groups",knownPendingIds=null,registrationWatchTimer=null;

// Ngăn menu chuột phải và các phím tắt mở DevTools thông dụng với Thành viên/Tổ trưởng.
// Đây chỉ là biện pháp hạn chế ở giao diện; quyền sửa điểm luôn được xác thực tại Worker.
function isRestrictedRole(){return !!me&&["member","leader"].includes(me.role)}
document.addEventListener("contextmenu",event=>{
  if(!isRestrictedRole())return;
  event.preventDefault();
  toast("Menu chuột phải đã bị tắt đối với tài khoản Thành viên/Tổ trưởng.");
},true);
document.addEventListener("keydown",event=>{
  if(!isRestrictedRole())return;
  const key=String(event.key||"").toLowerCase();
  const modifier=event.ctrlKey||event.metaKey;
  const inspectShortcut=key==="f12"
    ||(modifier&&event.shiftKey&&["i","j","c"].includes(key))
    ||(modifier&&key==="u")
    ||key==="contextmenu"
    ||(event.shiftKey&&key==="f10");
  if(!inspectShortcut)return;
  event.preventDefault();
  event.stopImmediatePropagation();
  toast("Phím tắt công cụ nhà phát triển đã bị hạn chế.");
},true);
const roles={founder:"Người sáng lập",teacher:"Giáo viên chủ nhiệm",leader:"Tổ trưởng",member:"Thành viên"};
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const n=v=>Number(v||0).toLocaleString("vi-VN",{maximumFractionDigits:2});
const fd=f=>Object.fromEntries(new FormData(f).entries());
function toast(s){let x=document.querySelector("#toast");x.textContent=s;x.classList.add("show");setTimeout(()=>x.classList.remove("show"),2800)}
async function api(path,method="GET",data){let r=await fetch(path,{method,credentials:"same-origin",headers:{"Content-Type":"application/json"},...(data===undefined?{}:{body:JSON.stringify(data)})});let j={};try{j=await r.json()}catch{}if(!r.ok)throw Error(j.error||"Yêu cầu không thành công");return j}
function field(label,name,type="text",placeholder=""){return '<label class="field">'+esc(label)+'<input name="'+name+'" type="'+type+'" placeholder="'+esc(placeholder)+'" required></label>'}
function groupsel(){return '<label class="field">Tổ<select name="group_no" required><option value="1">Tổ 1</option><option value="2">Tổ 2</option><option value="3">Tổ 3</option><option value="4">Tổ 4</option></select></label>'}
function authForm(title,desc,fields,button,submit,link){
  app.innerHTML='<section class="auth"><div class="card"><div class="auth-heading"><span class="auth-mark">ĐT</span><p class="eyebrow">QUẢN LÝ LỚP HỌC</p></div><h1>'+title+'</h1><p class="muted">'+desc+'</p><form id="f" class="form">'+fields+'<button class="btn auth-submit" type="submit">'+button+' <span aria-hidden="true">→</span></button></form>'+(link?'<div class="auth-links">'+link+'</div>':"")+'</div></section>';
  document.querySelector("#f").onsubmit=async e=>{e.preventDefault();try{await submit(fd(e.target))}catch(x){toast(x.message)}}
}
function login(){authForm("Đăng nhập","Sử dụng số điện thoại và mật khẩu đã đăng ký.",field("Số điện thoại","phone","tel")+field("Mật khẩu","password","password"),"Đăng nhập",async d=>{await api("/api/login","POST",d);await start()},'<button class="btn link" id="reg">Chưa có tài khoản? Đăng ký</button>');document.querySelector("#reg").onclick=register}
function register(){authForm("Đăng ký thành viên","Tài khoản mới luôn phải được người quản trị duyệt.",field("Họ và tên","full_name")+field("Số điện thoại","phone","tel")+groupsel()+field("Mật khẩu (8–128 ký tự)","password","password"),"Gửi đăng ký",async d=>{await api("/api/register","POST",d);toast("Đã gửi đăng ký. Vui lòng chờ duyệt.");login()},'<button class="btn link" id="back">Quay lại đăng nhập</button>');document.querySelector("#back").onclick=login}
function bootstrap(){authForm("Thiết lập người sáng lập","Nhập mã FOUNDER_SETUP_TOKEN đã đặt trong Cloudflare Secrets.",field("Mã thiết lập","setup_token","password")+field("Họ và tên","full_name")+field("Số điện thoại","phone","tel")+field("Mật khẩu","password","password"),"Tạo tài khoản",async d=>{await api("/api/bootstrap","POST",d);toast("Đã tạo tài khoản người sáng lập.");await start()})}
async function start(){try{let status=await api("/api/bootstrap/status");try{me=(await api("/api/me")).user;bar();await dashboard();return}catch{}userbar.innerHTML="";status.founder_exists?login():bootstrap()}catch(e){app.innerHTML='<div class="card"><h2>Chưa kết nối được hệ thống</h2><p>'+esc(e.message)+'</p></div>'}}
function bar(){
  const initials=String(me.full_name||"").trim().split(/\s+/).slice(-2).map(x=>x[0]||"").join("").toUpperCase();
  userbar.innerHTML='<div class="user-menu"><div class="user-avatar" aria-hidden="true">'+esc(initials||"TV")+'</div><div class="user-identity"><strong>'+esc(me.full_name)+'</strong><small>'+esc(roles[me.role])+'</small></div><button class="btn logout-btn" id="logout" type="button"><span aria-hidden="true">↪</span> Đăng xuất</button></div>';
  document.querySelector("#logout").onclick=async()=>{stopRegistrationWatch();try{await api("/api/logout","POST",{})}finally{me=null;start()}}
}
async function dashboard(){
  bar();
  try{
    let d=await api("/api/dashboard");
    if(d.personal){
      app.innerHTML=
        '<div class="chess-shell member-shell"><aside class="chess-sidebar"><div class="sidebar-brand"><span class="sidebar-orb">ĐT</span><div><strong>KHÔNG GIAN CỦA BẠN</strong><small>Điều hướng cá nhân</small></div></div><div class="sidebar-section-label">CÁ NHÂN</div><div class="side-link side-link-static is-active"><span class="side-icon">▦</span><span class="side-copy"><strong>Bảng điểm của tôi</strong><small>Kết quả và nhận xét</small></span></div><div class="sidebar-divider"></div><div class="sidebar-section-label">TÀI KHOẢN</div><button class="side-link" id="member-change-password" type="button"><span class="side-icon">⚙</span><span class="side-copy"><strong>Đổi mật khẩu</strong><small>Bảo vệ tài khoản</small></span><span class="side-arrow">›</span></button><div class="sidebar-spacer"></div><div class="sidebar-user"><span class="sidebar-user-dot"></span><div><strong>'+esc(me.full_name)+'</strong><small>'+esc(roles[me.role])+'</small></div></div></aside><section class="chess-main"><div class="dashboard-head"><div class="page-intro"><p class="eyebrow">TỔNG QUAN CÁ NHÂN</p><h1>Xin chào, '+esc(me.full_name)+'</h1><p class="muted">Theo dõi điểm số và nhận xét của bạn tại đây.</p></div><span class="role-pill">'+esc(roles[me.role])+'</span></div>'+personal(d.personal)+'</section></div>';
      document.querySelector("#member-change-password").onclick=()=>passwordPanel(app.querySelector(".chess-main"));
      return;
    }
    if(me.role==="founder"){updatePendingRegistrations(d.pending_members||[]);startRegistrationWatch()}
    const count=d.groups.reduce((s,g)=>s+g.member_count,0);
    const points=d.groups.reduce((s,g)=>s+g.total_points,0);
    const canManage=["founder","teacher"].includes(me.role);
    const isFounder=me.role==="founder";
    const navButton=(key,icon,label,description,countLabel="")=>'<button class="side-link '+(tab===key?"is-active":"")+'" data-tab="'+key+'" type="button"'+(tab===key?' aria-current="page"':"")+'><span class="side-icon" aria-hidden="true">'+icon+'</span><span class="side-copy"><strong>'+label+'</strong><small>'+description+'</small></span>'+(countLabel?'<span class="side-count">'+countLabel+'</span>':'<span class="side-arrow" aria-hidden="true">›</span>')+'</button>';
    app.innerHTML=
      '<div class="chess-shell"><aside class="chess-sidebar" aria-label="Điều hướng chính"><div class="sidebar-brand"><span class="sidebar-orb">ĐT</span><div><strong>TRUNG TÂM LỚP HỌC</strong><small>Khu vực quản lý</small></div></div><div class="sidebar-section-label">KHÔNG GIAN LỚP</div><nav class="side-nav">'+
      navButton("groups","▦","Tổng quan","Các tổ và điểm số")+
      (canManage?navButton("accounts","♙","Tài khoản","Duyệt và quản lý",isFounder&&d.pending_members.length?String(d.pending_members.length):""):"")+
      (isFounder?navButton("audit","◷","Nhật ký","Lịch sử hoạt động"):"")+
      '</nav><div class="sidebar-divider"></div><div class="sidebar-section-label">CÀI ĐẶT</div><nav class="side-nav">'+
      navButton("password","⚙","Đổi mật khẩu","Bảo mật tài khoản")+
      '</nav><div class="sidebar-spacer"></div><div class="sidebar-user"><span class="sidebar-user-dot"></span><div><strong>'+esc(me.full_name)+'</strong><small>'+esc(roles[me.role])+'</small></div></div></aside>'+
      '<section class="chess-main"><div class="dashboard-head"><div class="page-intro"><p class="eyebrow">TỔNG QUAN LỚP HỌC</p><h1>Xin chào, '+esc(me.full_name)+'</h1><p class="muted">Theo dõi thành tích, điểm số và hoạt động của các tổ trong lớp.</p></div><div class="page-actions"><span class="role-pill">'+esc(roles[me.role])+'</span>'+(isFounder?'<button class="btn alt notification-btn" id="enable-notifications" type="button"><span aria-hidden="true">♧</span> Bật thông báo</button>':"")+'</div></div>'+
      '<div class="grid"><div class="stat"><span>Tổ quản lý</span><strong>'+d.groups.length+'</strong></div><div class="stat"><span>Thành viên</span><strong>'+count+'</strong></div><div class="stat"><span>Tổng điểm</span><strong>'+n(points)+'</strong></div><div class="stat"><span>Chờ duyệt</span><strong>'+d.pending_members.length+'</strong></div></div>'+
      (isFounder&&d.pending_members.length?'<section class="notice-card"><div class="notice-icon" aria-hidden="true">!</div><div class="notice-copy"><strong>Có '+d.pending_members.length+' đăng ký mới đang chờ duyệt</strong><p>Hãy xem thông tin và xác nhận tài khoản trước khi thành viên sử dụng hệ thống.</p></div><button class="btn" type="button" data-tab="accounts">Xem đăng ký <span aria-hidden="true">→</span></button></section>':"")+
      '<div class="section-toolbar"><div><p class="eyebrow">KHU VỰC LÀM VIỆC</p><h2 id="workspace-title">'+(tab==="accounts"?"Quản lý tài khoản":tab==="audit"?"Nhật ký quản trị":tab==="password"?"Cài đặt tài khoản":"Các tổ trong lớp")+'</h2></div><small>Chọn chức năng ở thanh bên trái</small></div><div id="panel" class="content-panel"></div></section></div>';
    document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{
      tab=b.dataset.tab;
      document.querySelectorAll(".side-link[data-tab]").forEach(x=>{
        const active=x.dataset.tab===tab;
        x.classList.toggle("is-active",active);
        if(active)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current");
      });
      const title=document.querySelector("#workspace-title");
      if(title)title.textContent=tab==="accounts"?"Quản lý tài khoản":tab==="audit"?"Nhật ký quản trị":tab==="password"?"Cài đặt tài khoản":"Các tổ trong lớp";
      panel();
    });
    const notifyButton=document.querySelector("#enable-notifications");
    if(notifyButton)notifyButton.onclick=async()=>{
      if(!("Notification" in window)){toast("Trình duyệt này không hỗ trợ thông báo.");return}
      const permission=await Notification.requestPermission();
      toast(permission==="granted"?"Đã bật thông báo đăng ký mới trên trình duyệt.":"Bạn chưa cấp quyền thông báo.");
      notifyButton.classList.toggle("is-enabled",permission==="granted");
    };
    panel(d);
  }catch(e){app.innerHTML='<div class="card error-card">'+esc(e.message)+'</div>'}
}
async function panel(data){if(!data)data=await api("/api/dashboard");let p=document.querySelector("#panel");if(!p)return;if(tab==="accounts"&&["founder","teacher"].includes(me.role))return accounts(p,data.pending_members);if(tab==="audit"&&me.role==="founder")return audit(p);if(tab==="password")return passwordPanel(p);return groups(p,data.groups)}
function updatePendingRegistrations(items){if(me?.role!=="founder")return;const list=Array.isArray(items)?items:[];if(knownPendingIds===null){knownPendingIds=new Set(list.map(x=>Number(x.id)));return}for(const item of list){const id=Number(item.id);if(!knownPendingIds.has(id)){knownPendingIds.add(id);const message="Có đăng ký mới: "+item.full_name+" · Tổ "+item.group_no;toast(message);if("Notification" in window&&Notification.permission==="granted")new Notification("Class Merit Hub",{body:message})}}}
function startRegistrationWatch(){if(me?.role!=="founder"||registrationWatchTimer!==null)return;registrationWatchTimer=setInterval(async()=>{try{const latest=await api("/api/dashboard");updatePendingRegistrations(latest.pending_members||[])}catch{}},30000)}
function stopRegistrationWatch(){if(registrationWatchTimer!==null){clearInterval(registrationWatchTimer);registrationWatchTimer=null}knownPendingIds=null}
function passwordPanel(el){el.innerHTML='<section class="card"><div class="row between"><h2>Đổi mật khẩu</h2><button class="btn alt" id="back-password">Quay lại</button></div><p class="muted">Nhập mật khẩu hiện tại và mật khẩu mới. Mật khẩu mới phải có từ 8 đến 128 ký tự.</p><form id="change-password" class="form">'+field("Mật khẩu hiện tại","old_password","password")+field("Mật khẩu mới","new_password","password")+field("Nhập lại mật khẩu mới","confirm_password","password")+'<button class="btn">Cập nhật mật khẩu</button></form></section>';el.querySelector("#back-password").onclick=dashboard;el.querySelector("#change-password").onsubmit=async e=>{e.preventDefault();const data=fd(e.target);if(data.new_password!==data.confirm_password){toast("Hai mật khẩu mới không khớp.");return}delete data.confirm_password;try{await api("/api/password/change","POST",data);toast("Đã đổi mật khẩu. Vui lòng đăng nhập lại.");stopRegistrationWatch();me=null;await start()}catch(x){toast(x.message)}}}
function groups(el,list){
  el.innerHTML='<div class="groups">'+list.map(g=>
    '<section class="card group-card"><div class="group-heading"><div class="group-title"><span class="group-symbol" aria-hidden="true">T'+g.group_no+'</span><div><h2>Tổ '+g.group_no+'</h2><small>'+g.member_count+' thành viên</small></div></div><div class="group-total"><strong>'+n(g.total_points)+'</strong><small>điểm</small></div></div>'+
    '<div class="member-list">'+(g.members.length?g.members.map(m=>
      '<div class="member"><div class="member-info"><strong>'+esc(m.full_name)+'</strong><small>'+esc(m.phone)+'</small></div><div class="member-actions"><span class="points-chip">'+n(m.total_points)+' <small>điểm</small></span><button class="btn alt member-open" data-member="'+m.id+'" type="button">Hồ sơ <span aria-hidden="true">→</span></button></div></div>'
    ).join(""):'<div class="empty">Chưa có thành viên trong tổ này.</div>')+'</div></section>'
  ).join("")+'</div>';
  el.querySelectorAll("[data-member]").forEach(b=>b.onclick=()=>member(Number(b.dataset.member)));
}
function personal(d){return '<div class="grid"><div class="stat"><span>Tổng điểm</span><strong>'+n(d.total_points)+'</strong></div><div class="stat"><span>Lần ghi điểm</span><strong>'+d.scores.length+'</strong></div><div class="stat"><span>Nhận xét</span><strong>'+d.evaluations.length+'</strong></div><div class="stat"><span>Tổ</span><strong>'+esc(d.member.group_no)+'</strong></div></div><section class="card"><h2>Lịch sử điểm</h2>'+scores(d.scores,false)+'</section><section class="card"><h2>Nhận xét</h2>'+evaluations(d.evaluations,false)+'</section>'}
async function member(id){
  try{
    let d=await api("/api/members/"+id),edit=me.role!=="member";
    app.innerHTML=
      '<section class="profile-head"><div class="profile-title"><p class="eyebrow">HỒ SƠ THÀNH VIÊN</p><h1>'+esc(d.member.full_name)+'</h1><p class="muted">Tổ '+d.member.group_no+' <span aria-hidden="true">·</span> '+esc(d.member.phone)+'</p></div><div class="profile-actions"><button class="btn alt" id="back" type="button"><span aria-hidden="true">←</span> Quay lại danh sách</button></div></section>'+
      '<div class="grid"><div class="stat"><span>Tổng điểm</span><strong>'+n(d.total_points)+'</strong></div><div class="stat"><span>Lần ghi điểm</span><strong>'+d.scores.length+'</strong></div><div class="stat"><span>Nhận xét</span><strong>'+d.evaluations.length+'</strong></div><div class="stat"><span>Tổ</span><strong>'+esc(d.member.group_no)+'</strong></div></div>'+
      '<div class="profile-content"><section class="card"><div class="section-title"><div><p class="eyebrow">THEO DÕI</p><h2>Lịch sử điểm</h2></div><span class="section-count">'+d.scores.length+' mục</span></div>'+scores(d.scores,edit)+'</section>'+
      '<section class="card"><div class="section-title"><div><p class="eyebrow">ĐÁNH GIÁ</p><h2>Nhận xét</h2></div><span class="section-count">'+d.evaluations.length+' mục</span></div>'+evaluations(d.evaluations,edit)+'</section></div>'+
      (edit?'<section class="card update-card"><div class="section-title"><div><p class="eyebrow">CẬP NHẬT HỒ SƠ</p><h2>Ghi nhận thi đua</h2><p class="muted">Chọn một thao tác bên dưới để cập nhật thông tin cho thành viên.</p></div></div><div class="editor-grid"><form id="score" class="editor-panel"><div class="editor-icon score-icon" aria-hidden="true">＋</div><h3>Ghi điểm cộng / trừ</h3><p class="muted">Ghi nhận thành tích hoặc vi phạm của thành viên.</p><label class="field">Điểm cộng/trừ<input name="points" type="number" min="-100" max="100" step=".5" placeholder="Ví dụ: 5 hoặc -2" required></label><label class="field">Loại điểm<select name="category"><option>Nề nếp</option><option>Học tập</option><option>Hoạt động</option><option>Kỷ luật</option><option>Khen thưởng</option><option>Khác</option></select></label><label class="field">Lý do/minh chứng<textarea name="note" placeholder="Mô tả lý do ghi nhận..." required minlength="3" maxlength="500"></textarea></label><button class="btn editor-submit" type="submit">Lưu điểm <span aria-hidden="true">→</span></button></form><form id="evaluation" class="editor-panel"><div class="editor-icon note-icon" aria-hidden="true">✎</div><h3>Viết nhận xét</h3><p class="muted">Để lại nhận xét giúp thành viên cải thiện.</p><label class="field">Nội dung nhận xét<textarea name="content" placeholder="Nhập nội dung nhận xét..." required minlength="3" maxlength="1000"></textarea></label><button class="btn alt editor-submit" type="submit">Lưu nhận xét <span aria-hidden="true">→</span></button></form></div></section>':"");
    document.querySelector("#back").onclick=dashboard;
    app.querySelectorAll("[data-score]").forEach(b=>b.onclick=async()=>{try{await api("/api/scores/"+b.dataset.score,"DELETE",{});member(id)}catch(e){toast(e.message)}});
    app.querySelectorAll("[data-eval]").forEach(b=>b.onclick=async()=>{try{await api("/api/evaluations/"+b.dataset.eval,"DELETE",{});member(id)}catch(e){toast(e.message)}});
    if(edit){
      document.querySelector("#score").onsubmit=async e=>{e.preventDefault();try{await api("/api/members/"+id+"/scores","POST",fd(e.target));toast("Đã lưu điểm");member(id)}catch(x){toast(x.message)}};
      document.querySelector("#evaluation").onsubmit=async e=>{e.preventDefault();try{await api("/api/members/"+id+"/evaluations","POST",fd(e.target));toast("Đã lưu nhận xét");member(id)}catch(x){toast(x.message)}};
    }
  }catch(e){toast(e.message)}
}
function scores(a,del){return a.length?a.map(s=>'<div class="record"><div class="row between"><b class="'+(s.points<0?"negative":"points")+'">'+(s.points>0?"+":"")+n(s.points)+' điểm</b><small>'+esc(s.created_at)+'</small></div><p><b>'+esc(s.category)+'</b> · '+esc(s.note)+'</p>'+(del?'<button class="btn link" data-score="'+s.id+'">Ẩn</button>':"")+'</div>').join(""):'<div class="empty">Chưa có dữ liệu điểm.</div>'}
function evaluations(a,del){return a.length?a.map(x=>'<div class="record"><p>'+esc(x.content)+'</p><small>'+esc(x.created_at)+'</small>'+(del?'<button class="btn link" data-eval="'+x.id+'">Ẩn nhận xét</button>':"")+'</div>').join(""):'<div class="empty">Chưa có nhận xét.</div>'}
async function accounts(el,pending){
  const canCreateTeacher=me.role==="founder";
  let accountData;
  try{accountData=await api("/api/accounts")}catch(e){el.innerHTML='<section class="card">'+esc(e.message)+'</section>';return}
  const accountRows=accountData.accounts||[];
  const accountsHtml=accountRows.length?accountRows.map(x=>{
    const status=!x.is_active?"Đã xóa":x.registration_status==="pending"?"Chờ duyệt":x.registration_status==="rejected"?"Đã từ chối":"Đang hoạt động";
    const group=x.group_no?"Tổ "+x.group_no:"Không thuộc tổ";
    const resetButton=me.role==="founder"&&x.role==="member"&&x.is_active&&x.registration_status==="approved"
      ? '<button class="btn alt" data-reset-password="'+x.id+'" data-account-name="'+esc(x.full_name)+'">Cấp mật khẩu tạm</button>' : "";
    const removeButton=me.role==="founder"&&x.role!=="founder"&&x.is_active
      ? '<button class="btn red" data-delete-account="'+x.id+'" data-account-name="'+esc(x.full_name)+'">Xóa tài khoản</button>' : "";
    const actions=resetButton||removeButton?'<div class="actions">'+resetButton+removeButton+'</div>':"";
    return '<div class="pending"><div><b>'+esc(x.full_name)+'</b><small> · '+esc(x.phone)+' · '+esc(x.role_label||roles[x.role]||x.role)+' · '+esc(group)+' · '+esc(status)+'</small></div>'+actions+'</div>';
  }).join(""):'<div class="empty">Chưa có tài khoản.</div>';
  el.innerHTML='<section class="card"><h2>Đăng ký chờ duyệt</h2>'+(pending.length?pending.map(x=>'<div class="pending"><div><b>'+esc(x.full_name)+'</b><small> · '+esc(x.phone)+' · Tổ '+x.group_no+'</small></div><div class="actions"><button class="btn" data-approve="'+x.id+'">Duyệt</button><button class="btn red" data-reject="'+x.id+'">Từ chối</button></div></div>').join(""):'<div class="empty">Không có đăng ký chờ duyệt.</div>')+'</section><section class="card"><h2>Danh sách tài khoản</h2><p class="muted">Tài khoản đã xóa không thể đăng nhập; lịch sử điểm và nhận xét vẫn được giữ. Mật khẩu gốc không thể xem lại; Người sáng lập có thể cấp mật khẩu tạm mới cho thành viên đã được duyệt.</p>'+accountsHtml+'</section><section class="card"><h2>Tạo tài khoản</h2><form id="create" class="form">'+field("Họ và tên","full_name")+field("Số điện thoại","phone","tel")+field("Mật khẩu","password","password")+'<label class="field">Vai trò<select name="role" id="create-role"><option value="member">Thành viên</option><option value="leader">Tổ trưởng</option>'+(canCreateTeacher?'<option value="teacher">Giáo viên chủ nhiệm</option>':"")+'</select></label><div id="group-field">'+groupsel()+'</div><p id="teacher-role-note" class="muted" hidden>Giáo viên chủ nhiệm quản lý toàn bộ lớp và không thuộc Tổ 1, 2, 3 hoặc 4.</p><button class="btn">Tạo tài khoản</button></form></section>';
  const roleSelect=el.querySelector("#create-role");
  const groupField=el.querySelector("#group-field");
  const groupSelect=el.querySelector('[name="group_no"]');
  const teacherNote=el.querySelector("#teacher-role-note");
  function syncRoleFields(){
    const isTeacher=roleSelect.value==="teacher";
    groupField.hidden=isTeacher;
    groupSelect.disabled=isTeacher;
    groupSelect.required=!isTeacher;
    teacherNote.hidden=!isTeacher;
    if(isTeacher)groupSelect.value="";
  }
  roleSelect.addEventListener("change",syncRoleFields);
  syncRoleFields();
  el.querySelectorAll("[data-approve]").forEach(b=>b.onclick=async()=>{
    try{await api("/api/accounts/"+b.dataset.approve+"/approve","POST",{});await dashboard()}catch(e){toast(e.message)}
  });
  el.querySelectorAll("[data-reject]").forEach(b=>b.onclick=async()=>{
    if(!confirm("Từ chối đăng ký?"))return;
    try{await api("/api/accounts/"+b.dataset.reject+"/reject","POST",{});await dashboard()}catch(e){toast(e.message)}
  });
  el.querySelectorAll("[data-reset-password]").forEach(b=>b.onclick=async()=>{
    if(!confirm('Cấp một mật khẩu tạm mới cho "'+b.dataset.accountName+'"? Mật khẩu hiện tại sẽ mất hiệu lực.'))return;
    try{
      const result=await api("/api/accounts/"+b.dataset.resetPassword+"/reset-password","POST",{});
      if(!result.temporary_password)throw Error("Máy chủ không trả về mật khẩu tạm.");
      window.prompt("Mật khẩu tạm cho "+b.dataset.accountName+". Hãy sao chép và gửi riêng cho thành viên. Mật khẩu này chỉ hiển thị một lần:",result.temporary_password);
      toast("Đã cấp mật khẩu tạm; mật khẩu cũ đã bị thu hồi.");
      await accounts(el,pending);
    }catch(e){toast(e.message)}
  });
  el.querySelectorAll("[data-delete-account]").forEach(b=>b.onclick=async()=>{
    if(!confirm('Xóa tài khoản "'+b.dataset.accountName+'"? Người này sẽ không thể đăng nhập nữa. Lịch sử điểm và nhận xét sẽ được giữ lại.'))return;
    try{await api("/api/accounts/"+b.dataset.deleteAccount,"DELETE",{});toast("Đã xóa tài khoản (đã khóa đăng nhập).");await dashboard()}catch(e){toast(e.message)}
  });
  document.querySelector("#create").onsubmit=async e=>{
    e.preventDefault();
    try{const data=fd(e.target);if(data.role==="teacher")delete data.group_no;await api("/api/accounts","POST",data);toast("Đã tạo tài khoản");await dashboard()}catch(x){toast(x.message)}
  };
}
async function audit(el){
try{
let d=await api("/api/audit");
el.innerHTML='<section class="card"><div class="row between"><div><h2>Nhật ký quản trị</h2><p class="muted">Xóa một mục hoặc dọn toàn bộ nhật ký. Hệ thống vẫn lưu lại thao tác xóa để bảo đảm khả năng truy vết.</p></div>'+(d.logs.length?'<button class="btn red" id="clear-audit">Xóa toàn bộ nhật ký</button>':"")+'</div>'+(d.logs.length?d.logs.map(x=>'<div class="record"><div class="row between"><b>'+esc(x.action==="member_registration"?"Đăng ký tài khoản mới":x.action)+'</b><small>'+esc(x.created_at)+'</small></div><p>'+esc(x.details)+'</p><small>'+esc(x.actor_name)+'</small><div><button class="btn link" data-delete-audit="'+x.id+'">Xóa nhật ký này</button></div></div>').join(""):'<div class="empty">Chưa có nhật ký.</div>')+'</section>';
el.querySelectorAll("[data-delete-audit]").forEach(b=>b.onclick=async()=>{
if(!confirm("Xóa nhật ký này? Hệ thống sẽ ghi thêm một dòng để ghi nhận thao tác xóa."))return;
try{await api("/api/audit/"+b.dataset.deleteAudit,"DELETE",{});toast("Đã xóa nhật ký.");await audit(el)}catch(e){toast(e.message)}
});
const clearButton=el.querySelector("#clear-audit");
if(clearButton)clearButton.onclick=async()=>{
if(!confirm("Bạn chắc chắn muốn xóa toàn bộ nhật ký hiện có? Hệ thống sẽ giữ lại một dòng ghi nhận việc dọn nhật ký."))return;
try{await api("/api/audit","DELETE",{});toast("Đã dọn nhật ký cũ.");await audit(el)}catch(e){toast(e.message)}
};
}catch(e){el.innerHTML='<div class="card">'+esc(e.message)+'</div>'}
}

start();
