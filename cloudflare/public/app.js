const app=document.querySelector("#app"),userbar=document.querySelector("#userbar"),topnav=document.querySelector("#topnav");let me=null,tab="groups",knownPendingIds=null,registrationWatchTimer=null,presenceWatchTimer=null,presencePanelTimer=null;

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
function login(){authForm("Đăng nhập","Sử dụng tên đăng nhập được cấp hoặc số điện thoại đã đăng ký.",field("Tên đăng nhập hoặc số điện thoại","phone","text","Nhập tên đăng nhập hoặc số điện thoại")+field("Mật khẩu","password","password"),"Đăng nhập",async d=>{await api("/api/login","POST",d);await start()},'<button class="btn link" id="reg">Chưa có tài khoản? Đăng ký</button>');document.querySelector("#reg").onclick=register}
function register(){authForm("Đăng ký thành viên","Tài khoản mới luôn phải được người quản trị duyệt. Nếu họ tên có trong danh sách lớp, hệ thống sẽ tự xếp đúng tổ theo danh sách.",field("Họ và tên","full_name")+field("Số điện thoại","phone","tel")+groupsel()+field("Mật khẩu (8–128 ký tự)","password","password"),"Gửi đăng ký",async d=>{await api("/api/register","POST",d);toast("Đã gửi đăng ký. Vui lòng chờ duyệt.");login()},'<button class="btn link" id="back">Quay lại đăng nhập</button>');document.querySelector("#back").onclick=login}
function bootstrap(){authForm("Thiết lập người sáng lập","Nhập mã FOUNDER_SETUP_TOKEN đã đặt trong Cloudflare Secrets.",field("Mã thiết lập","setup_token","password")+field("Họ và tên","full_name")+field("Số điện thoại","phone","tel")+field("Mật khẩu","password","password"),"Tạo tài khoản",async d=>{await api("/api/bootstrap","POST",d);toast("Đã tạo tài khoản người sáng lập.");await start()})}
async function start(){try{let status=await api("/api/bootstrap/status");try{me=(await api("/api/me")).user;bar();await dashboard();return}catch{}userbar.innerHTML="";if(topnav)topnav.innerHTML="";status.founder_exists?login():bootstrap()}catch(e){app.innerHTML='<div class="card"><h2>Chưa kết nối được hệ thống</h2><p>'+esc(e.message)+'</p></div>'}}
function bar(){
  const initials=String(me.full_name||"").trim().split(/\s+/).slice(-2).map(x=>x[0]||"").join("").toUpperCase();
  userbar.innerHTML='<div class="user-menu"><div class="user-avatar" aria-hidden="true">'+esc(initials||"TV")+'</div><div class="user-identity"><strong>'+esc(me.full_name)+'</strong><small>'+esc(roles[me.role])+'</small></div><button class="btn logout-btn" id="logout" type="button"><span aria-hidden="true">↪</span> Đăng xuất</button></div>';
  if(topnav){
    if(me.role==="member")topnav.innerHTML='<span class="fb-topnav-note">BẢNG ĐIỂM CÁ NHÂN</span>';
    else{
      const items=[["groups","⌂","Lớp học"]];
      if(["founder","teacher","leader"].includes(me.role))items.push(["weekly","▤","Điểm tuần"]);
      if(["founder","teacher"].includes(me.role))items.push(["presence","◉","Đang online"]);
      topnav.innerHTML=items.map(item=>'<button class="fb-top-link '+(tab===item[0]?"is-active":"")+'" data-tab="'+item[0]+'" type="button" title="'+item[2]+'"><span aria-hidden="true">'+item[1]+'</span><small>'+item[2]+'</small></button>').join("");
    }
  }
  document.querySelector("#logout").onclick=async()=>{stopRegistrationWatch();stopPresenceWatch();try{try{await api("/api/presence/leave","POST",{})}catch{}await api("/api/logout","POST",{})}finally{me=null;start()}}
}
async function dashboard(){
  bar();
  startPresenceWatch();
  try{
    let d=await api("/api/dashboard");
    if(d.personal){
      app.innerHTML=
        '<div class="chess-shell member-shell"><aside class="chess-sidebar"><div class="sidebar-brand"><div class="sidebar-orb">ĐT</div><div><strong>KHÔNG GIAN CỦA BẠN</strong><small>Lớp 12A1</small></div></div><div class="sidebar-section-label">CÁ NHÂN</div><div class="side-link side-link-static is-active"><span class="side-icon">▦</span><span class="side-copy"><strong>Bảng điểm của tôi</strong><small>Kết quả và nhận xét</small></span></div><div class="sidebar-spacer"></div><div class="sidebar-user"><span class="sidebar-user-dot"></span><div><strong>'+esc(me.full_name)+'</strong><small>'+esc(roles[me.role])+'</small></div></div></aside><section class="chess-main"><div class="dashboard-head"><div class="page-intro"><p class="eyebrow">BẢNG TIN CÁ NHÂN</p><h1>Xin chào, '+esc(me.full_name)+'</h1><p class="muted">Theo dõi điểm thi đua và các nhận xét của bạn.</p></div><span class="role-pill">'+esc(roles[me.role])+'</span></div>'+personal(d.personal)+'</section><aside class="fb-right-sidebar"><section class="fb-right-card"><h3>Tóm tắt của bạn</h3><div class="fb-right-highlight"><span class="fb-right-icon">★</span><div><small>Tổng điểm hiện tại</small><strong>'+n(d.personal.total_points)+' điểm</strong></div></div><div class="fb-right-line"><span>Tổ đang tham gia</span><strong>Tổ '+esc(d.personal.member.group_no)+'</strong></div><div class="fb-right-line"><span>Lượt ghi điểm</span><strong>'+d.personal.scores.length+'</strong></div><div class="fb-right-line"><span>Nhận xét</span><strong>'+d.personal.evaluations.length+'</strong></div></section><section class="fb-right-card"><h3>Thông tin lớp</h3><p class="fb-right-copy">Điểm số và nhận xét được cập nhật bởi Tổ trưởng, Giáo viên chủ nhiệm hoặc Người sáng lập theo quyền được cấp.</p></section></aside></div>';

      return;
    }
    if(me.role==="founder"){updatePendingRegistrations(d.pending_members||[]);startRegistrationWatch()}
    const count=d.groups.reduce((s,g)=>s+g.member_count,0);
    const points=d.groups.reduce((s,g)=>s+g.total_points,0);
    const canManage=["founder","teacher"].includes(me.role);
    const canUpdateWeekly=["founder","teacher","leader"].includes(me.role);
    const isFounder=me.role==="founder";
    const rightSidebar='<aside class="fb-right-sidebar"><section class="fb-right-card"><div class="fb-right-card-head"><h3>Các tổ trong lớp</h3><span>12A1</span></div>'+d.groups.map(group=>'<div class="fb-right-group"><span class="fb-right-group-symbol">T'+group.group_no+'</span><div><strong>Tổ '+group.group_no+'</strong><small>'+group.member_count+' thành viên · '+(group.leader?esc(group.leader.full_name):"Chưa có tổ trưởng")+'</small></div></div>').join("")+'</section><section class="fb-right-card"><h3>Không gian quản lý</h3><p class="fb-right-copy">Theo dõi điểm thi đua, quản lý thành viên và cập nhật hoạt động lớp học tại các mục điều hướng.</p><div class="fb-right-line"><span>Vai trò của bạn</span><strong>'+esc(roles[me.role])+'</strong></div></section></aside>';
    const navButton=(key,icon,label,description,countLabel="")=>'<button class="side-link '+(tab===key?"is-active":"")+'" data-tab="'+key+'" type="button"'+(tab===key?' aria-current="page"':"")+'><span class="side-icon" aria-hidden="true">'+icon+'</span><span class="side-copy"><strong>'+label+'</strong><small>'+description+'</small></span>'+(countLabel?'<span class="side-count">'+countLabel+'</span>':'<span class="side-arrow" aria-hidden="true">›</span>')+'</button>';
    app.innerHTML=
      '<div class="chess-shell"><aside class="chess-sidebar" aria-label="Điều hướng chính"><div class="sidebar-brand"><span class="sidebar-orb">ĐT</span><div><strong>TRUNG TÂM LỚP HỌC</strong><small>Khu vực quản lý</small></div></div><div class="sidebar-section-label">KHÔNG GIAN LỚP</div><nav class="side-nav">'+
      navButton("groups","▦","Tổng quan","Các tổ và điểm số")+
      (canUpdateWeekly?navButton("weekly","▤","Điểm theo tuần","Nhập điểm từ thứ Hai đến Chủ nhật"):"")+
      (canManage?navButton("accounts","♙","Tài khoản","Duyệt và quản lý",isFounder&&d.pending_members.length?String(d.pending_members.length):""):"")+
      (canManage?navButton("assignments","♜","Phân công tổ","Tổ trưởng và thành viên"):"")+
      (canManage?navButton("presence","◉","Đang online","Ai đang hoạt động trong lớp"):"")+
      (isFounder?navButton("audit","◷","Nhật ký","Lịch sử hoạt động"):"")+
      '</nav>'+(canManage?'<div class="sidebar-divider"></div><div class="sidebar-section-label">BÁO CÁO</div><a class="side-link export-side-link" href="/api/export/merit.xlsx" download="diem-thi-dua-lop.xlsx" aria-label="Xuất dữ liệu điểm thi đua ra file Excel"><span class="side-icon" aria-hidden="true">⇩</span><span class="side-copy"><strong>Xuất dữ liệu Excel</strong><small>Tải báo cáo điểm của lớp</small></span><span class="side-arrow" aria-hidden="true">↓</span></a>':"")+'<div class="sidebar-divider"></div><div class="sidebar-section-label">CÀI ĐẶT</div><nav class="side-nav">'+
      (canManage?navButton("password","⚙","Đổi mật khẩu","Bảo mật tài khoản"):"")+
      '</nav><div class="sidebar-spacer"></div><div class="sidebar-user"><span class="sidebar-user-dot"></span><div><strong>'+esc(me.full_name)+'</strong><small>'+esc(roles[me.role])+'</small></div></div></aside>'+
      '<section class="chess-main"><div class="dashboard-head"><div class="page-intro"><p class="eyebrow">TỔNG QUAN LỚP HỌC</p><h1>Xin chào, '+esc(me.full_name)+'</h1><p class="muted">Theo dõi thành tích, điểm số và hoạt động của các tổ trong lớp.</p></div><div class="page-actions"><span class="role-pill">'+esc(roles[me.role])+'</span>'+(isFounder?'<button class="btn alt notification-btn" id="enable-notifications" type="button"><span aria-hidden="true">♧</span> Bật thông báo</button>':"")+'</div></div>'+
      '<div class="grid"><div class="stat"><span>Tổ quản lý</span><strong>'+d.groups.length+'</strong></div><div class="stat"><span>Học sinh trong danh sách</span><strong>'+count+'</strong></div><div class="stat"><span>Tổng điểm</span><strong>'+n(points)+'</strong></div><div class="stat"><span>Chờ duyệt</span><strong>'+d.pending_members.length+'</strong></div></div>'+
      (isFounder&&d.pending_members.length?'<section class="notice-card"><div class="notice-icon" aria-hidden="true">!</div><div class="notice-copy"><strong>Có '+d.pending_members.length+' đăng ký mới đang chờ duyệt</strong><p>Hãy xem thông tin và xác nhận tài khoản trước khi thành viên sử dụng hệ thống.</p></div><button class="btn" type="button" data-tab="accounts">Xem đăng ký <span aria-hidden="true">→</span></button></section>':"")+
      '<div class="section-toolbar"><div><p class="eyebrow">KHU VỰC LÀM VIỆC</p><h2 id="workspace-title">'+(tab==="weekly"?"Điểm thi đua theo tuần":tab==="presence"?"Trạng thái online":tab==="accounts"?"Quản lý tài khoản":tab==="assignments"?"Phân công tổ":tab==="audit"?"Nhật ký quản trị":tab==="password"?"Cài đặt tài khoản":"Các tổ trong lớp")+'</h2></div><small>Chọn chức năng ở thanh bên trái</small></div><div id="panel" class="content-panel"></div></section>'+rightSidebar+'</div>';
    document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{
      tab=b.dataset.tab;
      document.querySelectorAll(".side-link[data-tab]").forEach(x=>{
        const active=x.dataset.tab===tab;
        x.classList.toggle("is-active",active);
        if(active)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current");
      });
      document.querySelectorAll(".fb-top-link").forEach(x=>x.classList.toggle("is-active",x.dataset.tab===tab));
      const title=document.querySelector("#workspace-title");
      if(title)title.textContent=tab==="weekly"?"Điểm thi đua theo tuần":tab==="presence"?"Trạng thái online":tab==="accounts"?"Quản lý tài khoản":tab==="assignments"?"Phân công tổ":tab==="audit"?"Nhật ký quản trị":tab==="password"?"Cài đặt tài khoản":"Các tổ trong lớp";
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
async function panel(data){if(presencePanelTimer!==null&&tab!=="presence"){clearInterval(presencePanelTimer);presencePanelTimer=null}if(!data)data=await api("/api/dashboard");let p=document.querySelector("#panel");if(!p)return;if(tab==="presence"&&["founder","teacher"].includes(me.role))return presencePanel(p);if(tab==="weekly"&&["founder","teacher","leader"].includes(me.role))return weeklyPanel(p);if(tab==="accounts"&&["founder","teacher"].includes(me.role))return accounts(p,data.pending_members);if(tab==="assignments"&&["founder","teacher"].includes(me.role))return assignmentsPanel(p);if(tab==="audit"&&me.role==="founder")return audit(p);if(tab==="password"&&["founder","teacher"].includes(me.role))return passwordPanel(p);if(tab==="password")tab="groups";return groups(p,data.groups)}
function startPresenceWatch(){
  if(!me||presenceWatchTimer!==null)return;
  const ping=async()=>{
    if(!me||document.visibilityState==="hidden")return;
    try{await api("/api/presence/ping","POST",{})}catch{}
  };
  ping();
  presenceWatchTimer=setInterval(ping,30000);
}
function stopPresenceWatch(){
  if(presenceWatchTimer!==null){clearInterval(presenceWatchTimer);presenceWatchTimer=null}
  if(presencePanelTimer!==null){clearInterval(presencePanelTimer);presencePanelTimer=null}
}
document.addEventListener("visibilitychange",()=>{
  if(document.visibilityState==="visible"&&me)api("/api/presence/ping","POST",{}).catch(()=>{});
});
function presenceLastSeen(timestamp,serverTime){
  const value=Number(timestamp||0);
  if(!value)return "Chưa có lần hoạt động";
  const seconds=Math.max(0,Number(serverTime)-value);
  if(seconds<45)return "Vừa hoạt động";
  if(seconds<60)return seconds+" giây trước";
  const minutes=Math.floor(seconds/60);
  if(minutes<60)return minutes+" phút trước";
  const hours=Math.floor(minutes/60);
  if(hours<24)return hours+" giờ trước";
  return new Date(value*1000).toLocaleString("vi-VN",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
}
async function presencePanel(el){
  if(presencePanelTimer!==null){clearInterval(presencePanelTimer);presencePanelTimer=null}
  async function render(){
    try{
      const data=await api("/api/presence");
      const groupHtml=data.groups.map(group=>{
        const rows=group.members.map(person=>
          '<div class="presence-person">'+
            '<div class="presence-person-main"><span class="presence-dot '+(person.online?"is-online":"is-offline")+'"></span>'+
            '<div class="presence-identity"><strong>'+esc(person.full_name)+'</strong><small>'+esc(person.role_label)+' · Tổ '+group.group_no+'</small></div></div>'+
            '<span class="presence-state '+(person.online?"is-online":"is-offline")+'">'+(person.online?"Đang online":"Offline")+'</span>'+
            '<small class="presence-last-seen">'+(person.online?"Hoạt động: ":"Lần cuối: ")+esc(presenceLastSeen(person.last_seen,data.server_time))+'</small>'+
          '</div>'
        ).join("");
        return '<section class="card presence-group-card"><div class="presence-group-heading"><div><span class="group-symbol">T'+group.group_no+'</span><div><p class="eyebrow">TRẠNG THÁI TỔ '+group.group_no+'</p><h3>Tổ '+group.group_no+'</h3></div></div><span class="presence-group-count">'+group.online_count+'/'+group.total+' online</span></div>'+
          (rows||'<div class="empty">Tổ này chưa có tài khoản thành viên hoạt động.</div>')+'</section>';
      }).join("");
      el.innerHTML=
        '<section class="presence-intro"><div><p class="eyebrow">THEO DÕI HOẠT ĐỘNG</p><h3>Thành viên đang online</h3><p>Tài khoản được tính là online khi có tín hiệu hoạt động trong 90 giây gần nhất. Danh sách tự làm mới sau mỗi 30 giây.</p></div><button class="btn alt" id="presence-refresh" type="button">↻ Làm mới</button></section>'+
        '<div class="presence-summary"><div class="presence-stat is-online"><small>Đang online</small><strong>'+data.online_count+'</strong></div><div class="presence-stat is-offline"><small>Đang offline</small><strong>'+data.offline_count+'</strong></div><div class="presence-stat"><small>Tổng tài khoản học sinh</small><strong>'+data.total+'</strong></div></div>'+
        '<div class="presence-groups">'+(groupHtml||'<section class="card"><div class="empty">Chưa có tài khoản học sinh đang hoạt động.</div></section>')+'</div>'+
        '<p class="presence-footnote">Trạng thái online dựa trên tín hiệu từ trình duyệt, không phải xác nhận chắc chắn rằng người dùng đang nhìn vào màn hình.</p>';
      el.querySelector("#presence-refresh").onclick=()=>render();
    }catch(error){
      el.innerHTML='<section class="card error-card">'+esc(error.message)+'</section>';
    }
  }
  await render();
  presencePanelTimer=setInterval(()=>{
    if(tab==="presence"&&el.isConnected)render();
  },30000);
}
function updatePendingRegistrations(items){if(me?.role!=="founder")return;const list=Array.isArray(items)?items:[];if(knownPendingIds===null){knownPendingIds=new Set(list.map(x=>Number(x.id)));return}for(const item of list){const id=Number(item.id);if(!knownPendingIds.has(id)){knownPendingIds.add(id);const message="Có đăng ký mới: "+item.full_name+" · Tổ "+item.group_no;toast(message);if("Notification" in window&&Notification.permission==="granted")new Notification("Class Merit Hub",{body:message})}}}
function startRegistrationWatch(){if(me?.role!=="founder"||registrationWatchTimer!==null)return;registrationWatchTimer=setInterval(async()=>{try{const latest=await api("/api/dashboard");updatePendingRegistrations(latest.pending_members||[])}catch{}},30000)}
function stopRegistrationWatch(){if(registrationWatchTimer!==null){clearInterval(registrationWatchTimer);registrationWatchTimer=null}knownPendingIds=null}
function localIsoDate(d){return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0")}
function mondayOfWeek(value){
  const d=new Date(value+"T12:00:00");
  if(Number.isNaN(d.getTime()))return mondayOfWeek(localIsoDate(new Date()));
  d.setDate(d.getDate()-((d.getDay()+6)%7));
  return localIsoDate(d);
}
function shiftIsoDate(value,amount){const d=new Date(value+"T12:00:00");d.setDate(d.getDate()+amount);return localIsoDate(d)}
function shortDate(value){return new Date(value+"T12:00:00").toLocaleDateString("vi-VN",{day:"2-digit",month:"2-digit"})}
async function weeklyPanel(el){
  let weekStart=mondayOfWeek(localIsoDate(new Date()));
  const weekdays=["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ nhật"];
  async function render(){
    el.innerHTML='<section class="card"><p class="muted">Đang tải bảng điểm tuần...</p></section>';
    try{
      const data=await api("/api/weekly-scores?week_start="+encodeURIComponent(weekStart));
      const memberCount=data.groups.reduce((total,group)=>total+group.members.length,0);
      const filledCount=data.groups.reduce((total,group)=>total+group.filled_days,0);
      const totalPoints=data.groups.reduce((total,group)=>total+group.week_total,0);
      const groupHtml=data.groups.map(group=>{
        const rows=group.members.map(member=>{
          const cells=data.dates.map((day,index)=>{
            const value=member.days[day];
            return '<td><input class="week-point-input" type="number" inputmode="decimal" min="-100" max="100" step="0.5" data-member-id="'+member.id+'" data-score-date="'+day+'" data-original="'+(value===null?"":String(value))+'" value="'+(value===null?"":String(value))+'" aria-label="Điểm '+weekdays[index]+' của '+esc(member.full_name)+'" placeholder="—"></td>';
          }).join("");
          return '<tr data-week-row><td class="week-member-cell"><strong>'+esc(member.full_name)+'</strong><small>Đã nhập '+member.filled_days+'/7 ngày</small></td>'+cells+'<td class="week-total-cell" data-week-total>'+n(member.week_total)+'</td></tr>';
        }).join("");
        return '<section class="card weekly-group-card"><div class="weekly-group-heading"><div><span class="group-symbol">T'+group.group_no+'</span><div><p class="eyebrow">BẢNG ĐIỂM TỔ '+group.group_no+'</p><h3>Tổ '+group.group_no+'</h3></div></div><div class="weekly-group-total"><strong>'+n(group.week_total)+'</strong><small>điểm trong tuần</small></div></div><div class="weekly-table-wrap"><table class="weekly-table"><thead><tr><th>Thành viên</th>'+data.dates.map((day,index)=>'<th>'+weekdays[index]+'<small>'+shortDate(day)+'</small></th>').join("")+'<th>Tổng tuần</th></tr></thead><tbody>'+(rows||'<tr><td colspan="9" class="empty">Tổ này chưa có tài khoản thành viên hoạt động.</td></tr>')+'</tbody></table></div></section>';
      }).join("");
      el.innerHTML=
        '<section class="weekly-intro"><div><p class="eyebrow">THEO DÕI THI ĐUA</p><h3>Chấm điểm từng ngày trong tuần</h3><p>Tổ trưởng nhập điểm cho từng thành viên của tổ mình từ Thứ Hai đến Chủ nhật. Có thể nhập điểm âm, điểm dương hoặc 0; để trống nếu ngày đó chưa có điểm.</p></div><span class="weekly-intro-icon" aria-hidden="true">▦</span></section>'+
        '<section class="card weekly-control-card"><div class="weekly-controls"><button class="btn alt" id="week-prev" type="button" aria-label="Tuần trước">← Tuần trước</button><label class="field">Ngày bắt đầu tuần (Thứ Hai)<input id="week-picker" type="date" value="'+data.week_start+'"></label><button class="btn alt" id="week-next" type="button" aria-label="Tuần sau">Tuần sau →</button><button class="btn link" id="week-current" type="button">Tuần hiện tại</button></div><div class="weekly-overview"><span><small>Khoảng thời gian</small><strong>'+shortDate(data.week_start)+' – '+shortDate(data.week_end)+'</strong></span><span><small>Thành viên</small><strong>'+memberCount+'</strong></span><span><small>Ô điểm đã ghi</small><strong>'+filledCount+'</strong></span><span><small>Tổng điểm tuần</small><strong>'+n(totalPoints)+'</strong></span></div></section>'+
        (groupHtml||'<section class="card"><div class="empty">Chưa có thành viên đã được duyệt để chấm điểm.</div></section>')+
        '<div class="weekly-save-bar"><p class="muted">Ô trống sẽ được hiểu là chưa ghi điểm. Khi lưu, ô đã có điểm nhưng được xóa trắng sẽ bị xóa bản ghi của ngày đó.</p><button class="btn" id="save-week-scores" type="button">Lưu điểm cả tuần <span aria-hidden="true">→</span></button></div>';
      el.querySelector("#week-prev").onclick=()=>{weekStart=shiftIsoDate(weekStart,-7);render()};
      el.querySelector("#week-next").onclick=()=>{weekStart=shiftIsoDate(weekStart,7);render()};
      el.querySelector("#week-current").onclick=()=>{weekStart=mondayOfWeek(localIsoDate(new Date()));render()};
      el.querySelector("#week-picker").onchange=event=>{if(event.target.value){weekStart=mondayOfWeek(event.target.value);render()}};
      el.querySelectorAll(".week-point-input").forEach(input=>input.oninput=()=>{
        const row=input.closest("[data-week-row]");
        const sum=[...row.querySelectorAll(".week-point-input")].reduce((value,item)=>value+(item.value.trim()===""?0:Number(item.value||0)),0);
        row.querySelector("[data-week-total]").textContent=n(sum);
      });
      el.querySelector("#save-week-scores").onclick=async()=>{
        const inputs=[...el.querySelectorAll(".week-point-input")];
        const invalid=inputs.find(input=>!input.checkValidity());
        if(invalid){invalid.reportValidity();invalid.focus();return}
        const changedInputs=inputs.filter(input=>input.value.trim()!==input.dataset.original);
        if(!changedInputs.length){toast("Không có ô điểm nào thay đổi.");return}
        const scores=changedInputs.map(input=>({
          member_id:Number(input.dataset.memberId),
          date:input.dataset.scoreDate,
          points:input.value.trim()===""?null:Number(input.value)
        }));
        const button=el.querySelector("#save-week-scores");
        button.disabled=true;
        button.textContent="Đang lưu điểm...";
        try{
          const result=await api("/api/weekly-scores","POST",{week_start:weekStart,scores});
          toast("Đã lưu "+result.saved+" ô điểm; xóa "+result.removed+" ô trống.");
          await render();
        }catch(error){
          toast(error.message);
          button.disabled=false;
          button.innerHTML='Lưu điểm cả tuần <span aria-hidden="true">→</span>';
        }
      };
    }catch(error){
      el.innerHTML='<section class="card error-card">'+esc(error.message)+'</section>';
    }
  }
  await render();
}
function passwordPanel(el){el.innerHTML='<section class="card"><div class="row between"><h2>Đổi mật khẩu</h2><button class="btn alt" id="back-password">Quay lại</button></div><p class="muted">Nhập mật khẩu hiện tại và mật khẩu mới. Mật khẩu mới phải có từ 8 đến 128 ký tự.</p><form id="change-password" class="form">'+field("Mật khẩu hiện tại","old_password","password")+field("Mật khẩu mới","new_password","password")+field("Nhập lại mật khẩu mới","confirm_password","password")+'<button class="btn">Cập nhật mật khẩu</button></form></section>';el.querySelector("#back-password").onclick=dashboard;el.querySelector("#change-password").onsubmit=async e=>{e.preventDefault();const data=fd(e.target);if(data.new_password!==data.confirm_password){toast("Hai mật khẩu mới không khớp.");return}delete data.confirm_password;try{await api("/api/password/change","POST",data);toast("Đã đổi mật khẩu. Vui lòng đăng nhập lại.");stopRegistrationWatch();me=null;await start()}catch(x){toast(x.message)}}}
function groups(el,list){
  el.innerHTML='<div class="roster-note"><strong>Danh sách lớp 12A1</strong><span>Các tên đã được nhập theo danh sách giáo viên cung cấp. Học sinh chưa kích hoạt tài khoản vẫn hiển thị; chỉ tài khoản đã được duyệt mới có hồ sơ và chức năng ghi điểm.</span></div><div class="groups">'+list.map(g=>
    '<section class="card group-card"><div class="group-heading"><div class="group-title"><span class="group-symbol" aria-hidden="true">T'+g.group_no+'</span><div><h2>Tổ '+g.group_no+'</h2><small>'+g.member_count+' tên trong danh sách · '+(g.active_count||0)+' tài khoản hoạt động</small><small class="group-leader-label">Tổ trưởng: '+(g.leader?esc(g.leader.full_name):'Chưa phân công')+'</small></div></div><div class="group-total"><strong>'+n(g.total_points)+'</strong><small>điểm</small></div></div>'+
    '<div class="member-list">'+(g.members.length?g.members.map(m=>
      '<div class="member"><div class="member-info"><strong>'+esc(m.full_name)+'</strong><small>'+(m.id?esc(m.phone):esc(m.status_label||"Chưa kích hoạt tài khoản"))+'</small></div><div class="member-actions">'+(m.id?'<span class="points-chip">'+n(m.total_points)+' <small>điểm</small></span><button class="btn alt member-open" data-member="'+m.id+'" type="button">Hồ sơ <span aria-hidden="true">→</span></button>':'<span class="roster-status">'+esc(m.status_label||"Chưa kích hoạt")+'</span>')+'</div></div>'
    ).join(""):'<div class="empty">Chưa có thành viên trong tổ này.</div>')+'</div></section>'
  ).join("")+'</div>';
  el.querySelectorAll("[data-member]").forEach(b=>b.onclick=()=>member(Number(b.dataset.member)));
}
function personal(d){return '<div class="grid"><div class="stat"><span>Tổng điểm</span><strong>'+n(d.total_points)+'</strong></div><div class="stat"><span>Lần ghi điểm</span><strong>'+d.scores.length+'</strong></div><div class="stat"><span>Nhận xét</span><strong>'+d.evaluations.length+'</strong></div><div class="stat"><span>Tổ</span><strong>'+esc(d.member.group_no)+'</strong></div></div><section class="card"><h2>Lịch sử điểm</h2>'+scores(d.scores,false)+'</section><section class="card"><h2>Nhận xét</h2>'+evaluations(d.evaluations,false)+'</section>'}
async function member(id){
  try{
    let d=await api("/api/members/"+id),edit=me.role!=="member";
    app.innerHTML=
      '<div class="fb-profile-shell"><aside class="fb-profile-left"><div class="fb-profile-left-card"><span class="fb-profile-avatar">ĐT</span><strong>Hồ sơ thi đua</strong><small>Lớp 12A1</small><p>Thông tin và lịch sử ghi nhận của thành viên.</p></div></aside><div class="fb-profile-main"><section class="profile-head"><div class="profile-title"><p class="eyebrow">HỒ SƠ THÀNH VIÊN</p><h1>'+esc(d.member.full_name)+'</h1><p class="muted">Tổ '+d.member.group_no+' <span aria-hidden="true">·</span> '+esc(d.member.phone)+'</p></div><div class="profile-actions"><button class="btn alt" id="back" type="button"><span aria-hidden="true">←</span> Quay lại danh sách</button></div></section>'+
      '<div class="grid"><div class="stat"><span>Tổng điểm</span><strong>'+n(d.total_points)+'</strong></div><div class="stat"><span>Lần ghi điểm</span><strong>'+d.scores.length+'</strong></div><div class="stat"><span>Nhận xét</span><strong>'+d.evaluations.length+'</strong></div><div class="stat"><span>Tổ</span><strong>'+esc(d.member.group_no)+'</strong></div></div>'+
      '<div class="profile-content"><section class="card"><div class="section-title"><div><p class="eyebrow">THEO DÕI</p><h2>Lịch sử điểm</h2></div><span class="section-count">'+d.scores.length+' mục</span></div>'+scores(d.scores,edit)+'</section>'+
      '<section class="card"><div class="section-title"><div><p class="eyebrow">ĐÁNH GIÁ</p><h2>Nhận xét</h2></div><span class="section-count">'+d.evaluations.length+' mục</span></div>'+evaluations(d.evaluations,edit)+'</section></div>'+
      (edit?'<section class="card update-card"><div class="section-title"><div><p class="eyebrow">CẬP NHẬT HỒ SƠ</p><h2>Ghi nhận thi đua</h2><p class="muted">Chọn một thao tác bên dưới để cập nhật thông tin cho thành viên.</p></div></div><div class="editor-grid"><form id="score" class="editor-panel"><div class="editor-icon score-icon" aria-hidden="true">＋</div><h3>Ghi điểm cộng / trừ</h3><p class="muted">Ghi nhận thành tích hoặc vi phạm của thành viên.</p><label class="field">Điểm cộng/trừ<input name="points" type="number" min="-100" max="100" step=".5" placeholder="Ví dụ: 5 hoặc -2" required></label><label class="field">Loại điểm<select name="category"><option>Nề nếp</option><option>Học tập</option><option>Hoạt động</option><option>Kỷ luật</option><option>Khen thưởng</option><option>Khác</option></select></label><label class="field">Lý do/minh chứng<textarea name="note" placeholder="Mô tả lý do ghi nhận..." required minlength="3" maxlength="500"></textarea></label><button class="btn editor-submit" type="submit">Lưu điểm <span aria-hidden="true">→</span></button></form><form id="evaluation" class="editor-panel"><div class="editor-icon note-icon" aria-hidden="true">✎</div><h3>Viết nhận xét</h3><p class="muted">Để lại nhận xét giúp thành viên cải thiện.</p><label class="field">Nội dung nhận xét<textarea name="content" placeholder="Nhập nội dung nhận xét..." required minlength="3" maxlength="1000"></textarea></label><button class="btn alt editor-submit" type="submit">Lưu nhận xét <span aria-hidden="true">→</span></button></form></div></section>':"")+'<aside class="fb-right-sidebar"><section class="fb-right-card"><h3>Tổng quan hồ sơ</h3><div class="fb-right-highlight"><span class="fb-right-icon">★</span><div><small>Tổng điểm</small><strong>'+n(d.total_points)+' điểm</strong></div></div><div class="fb-right-line"><span>Số lượt ghi điểm</span><strong>'+d.scores.length+'</strong></div><div class="fb-right-line"><span>Nhận xét</span><strong>'+d.evaluations.length+'</strong></div><div class="fb-right-line"><span>Thuộc</span><strong>Tổ '+esc(d.member.group_no)+'</strong></div></section></aside></div></div>';
    document.querySelector("#back").onclick=dashboard;
    app.querySelectorAll("[data-score]").forEach(b=>b.onclick=async()=>{try{await api("/api/scores/"+b.dataset.score,"DELETE",{});member(id)}catch(e){toast(e.message)}});
    app.querySelectorAll("[data-eval]").forEach(b=>b.onclick=async()=>{try{await api("/api/evaluations/"+b.dataset.eval,"DELETE",{});member(id)}catch(e){toast(e.message)}});
    if(edit){
      document.querySelector("#score").onsubmit=async e=>{e.preventDefault();try{await api("/api/members/"+id+"/scores","POST",fd(e.target));toast("Đã lưu điểm");member(id)}catch(x){toast(x.message)}};
      document.querySelector("#evaluation").onsubmit=async e=>{e.preventDefault();try{await api("/api/members/"+id+"/evaluations","POST",fd(e.target));toast("Đã lưu nhận xét");member(id)}catch(x){toast(x.message)}};
    }
  }catch(e){toast(e.message)}
}
function scores(a,del){return a.length?a.map(s=>'<article class="record fb-record"><div class="fb-record-header"><span class="fb-record-avatar">ĐT</span><div class="fb-record-meta"><strong>Ghi nhận điểm thi đua</strong><small>'+esc(s.created_at)+'</small></div><span class="fb-score-pill '+(s.points<0?"is-negative":"is-positive")+'">'+(s.points>0?"+":"")+n(s.points)+' điểm</span></div><p class="fb-record-copy"><b>'+esc(s.category)+'</b><span> · </span>'+esc(s.note)+'</p>'+(del?'<div class="fb-record-actions"><button class="btn link" data-score="'+s.id+'">Ẩn bản ghi</button></div>':"")+'</article>').join(""):'<div class="empty">Chưa có dữ liệu điểm.</div>'}
function evaluations(a,del){return a.length?a.map(x=>'<article class="record fb-record fb-comment"><div class="fb-record-header"><span class="fb-record-avatar fb-comment-avatar">✎</span><div class="fb-record-meta"><strong>Nhận xét thi đua</strong><small>'+esc(x.created_at)+'</small></div></div><p class="fb-record-copy">'+esc(x.content)+'</p>'+(del?'<div class="fb-record-actions"><button class="btn link" data-eval="'+x.id+'">Ẩn nhận xét</button></div>':"")+'</article>').join(""):'<div class="empty">Chưa có nhận xét.</div>'}
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
  const bulkProvisionCard=me.role==="founder"?'<section class="card bulk-provision-card"><p class="eyebrow">KHỞI TẠO TÀI KHOẢN</p><h2>Tạo tài khoản cho học sinh lớp 12A1</h2><p class="muted">Tự động tạo tài khoản còn thiếu cho danh sách 47 học sinh. File Excel có tên đăng nhập và mật khẩu hiện đang dùng. Mật khẩu được lưu trong kho mã hóa AES-GCM để Người sáng lập có thể tải lại file khi bị mất. Chỉ tài khoản chưa có bản sao mật khẩu hợp lệ mới được cấp mật khẩu mới một lần; các lần xuất sau không đổi mật khẩu.</p><button class="btn" id="bulk-create-roster" type="button">Tạo / đồng bộ 47 tài khoản và tải lại file đăng nhập <span aria-hidden="true">↓</span></button></section>':"";
  const resettableAccounts=accountRows.filter(x=>(x.role==="member"||x.role==="leader")&&x.is_active&&x.registration_status==="approved");
  const bulkCredentialResetCard=me.role==="founder"?
    '<section class="card bulk-credential-reset-card"><div class="section-title"><div><p class="eyebrow">DỰ PHÒNG TÀI KHOẢN</p><h2>Sao lưu thông tin đăng nhập toàn lớp</h2><p class="muted">Tải lại file Excel chứa mật khẩu hiện đang sử dụng của từng tài khoản.</p></div><span class="section-count">'+resettableAccounts.length+' tài khoản</span></div>'+
    '<div class="credential-reset-warning"><strong>Những tài khoản đã có bản sao mã hóa hợp lệ sẽ không bị đổi mật khẩu</strong><p>Chỉ tài khoản chưa có bản sao, hoặc bản sao không còn khớp mật khẩu hiện tại, mới được cấp mật khẩu tạm mới và đăng xuất các phiên cũ. Người sáng lập và Giáo viên chủ nhiệm không bị ảnh hưởng.</p></div>'+
    '<p class="muted">Mật khẩu được mã hóa AES-GCM trong cơ sở dữ liệu, không lưu dạng văn bản thuần. File Excel chỉ tải xuống cho Người sáng lập; hãy lưu ở nơi an toàn và chỉ gửi mật khẩu cho đúng thành viên.</p>'+
    '<button class="btn" id="reset-all-student-passwords" type="button" '+(resettableAccounts.length?"":"disabled")+'>Xuất lại file thông tin đăng nhập <span aria-hidden="true">↓</span></button></section>':"";
  el.innerHTML=bulkProvisionCard+bulkCredentialResetCard+'<section class="card"><h2>Đăng ký chờ duyệt</h2>'+(pending.length?pending.map(x=>'<div class="pending"><div><b>'+esc(x.full_name)+'</b><small> · '+esc(x.phone)+' · Tổ '+x.group_no+'</small></div><div class="actions"><button class="btn" data-approve="'+x.id+'">Duyệt</button><button class="btn red" data-reject="'+x.id+'">Từ chối</button></div></div>').join(""):'<div class="empty">Không có đăng ký chờ duyệt.</div>')+'</section><section class="card"><h2>Danh sách tài khoản</h2><p class="muted">Tài khoản đã xóa không thể đăng nhập; lịch sử điểm và nhận xét vẫn được giữ. Mật khẩu gốc không thể xem lại; Người sáng lập có thể cấp mật khẩu tạm mới cho thành viên đã được duyệt.</p>'+accountsHtml+'</section><section class="card"><h2>Tạo tài khoản</h2><form id="create" class="form">'+field("Họ và tên","full_name")+field("Số điện thoại","phone","tel")+field("Mật khẩu","password","password")+'<label class="field">Vai trò<select name="role" id="create-role"><option value="member">Thành viên</option><option value="leader">Tổ trưởng</option>'+(canCreateTeacher?'<option value="teacher">Giáo viên chủ nhiệm</option>':"")+'</select></label><div id="group-field">'+groupsel()+'</div><p id="teacher-role-note" class="muted" hidden>Giáo viên chủ nhiệm quản lý toàn bộ lớp và không thuộc Tổ 1, 2, 3 hoặc 4.</p><button class="btn">Tạo tài khoản</button></form></section>';
  const resetAllButton=el.querySelector("#reset-all-student-passwords");
  if(resetAllButton)resetAllButton.onclick=async()=>{
    const count=resettableAccounts.length;
    if(!count){toast("Không có tài khoản học sinh đang hoạt động để xuất thông tin đăng nhập.");return}
    if(!confirm("Xuất lại file cho "+count+" tài khoản học sinh đang hoạt động? Những tài khoản đã có bản sao mật khẩu hợp lệ sẽ giữ nguyên mật khẩu và phiên đăng nhập. Chỉ tài khoản chưa có bản sao hợp lệ mới được cấp mật khẩu tạm mới. Tiếp tục?"))return;
    const confirmation=window.prompt('Để xác nhận, hãy nhập chính xác: CAP LAI MAT KHAU TOAN LOP');
    if(confirmation!=="CAP LAI MAT KHAU TOAN LOP"){
      if(confirmation!==null)toast("Nội dung xác nhận không chính xác. Chưa có mật khẩu nào bị thay đổi.");
      return;
    }
    resetAllButton.disabled=true;
    resetAllButton.textContent="Đang tạo file Excel...";
    try{
      const response=await fetch("/api/accounts/reset-all-student-passwords",{
        method:"POST",
        credentials:"same-origin",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({confirmation:"CAP_LAI_MAT_KHAU_TOAN_LOP"})
      });
      if(!response.ok){
        let message="Không thể xuất lại file thông tin đăng nhập.";
        try{const data=await response.json();message=data.error||message}catch{}
        throw Error(message);
      }
      const file=await response.blob();
      const fileUrl=URL.createObjectURL(file);
      const link=document.createElement("a");
      const disposition=response.headers.get("Content-Disposition")||"";
      const filenameMatch=disposition.match(/filename="?([^";]+)"?/i);
      link.href=fileUrl;
      link.download=filenameMatch?filenameMatch[1]:"tai-khoan-dang-nhap-12A1.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(()=>URL.revokeObjectURL(fileUrl),1500);
      const updatedCount=Number(response.headers.get("X-Password-Reset-Count")||0);
      const credentialCount=Number(response.headers.get("X-Credential-Count")||count);
      const auditWarning=response.headers.get("X-Audit-Recorded")==="false"?" Lưu ý: nhật ký quản trị chưa ghi được thao tác này.":"";
      toast("Đã xuất file Excel cho "+credentialCount+" tài khoản; chỉ cấp mật khẩu mới cho "+updatedCount+" tài khoản chưa có bản sao hợp lệ."+auditWarning);
      await dashboard();
    }catch(error){
      toast(error.message);
      resetAllButton.disabled=false;
      resetAllButton.textContent="Xuất lại file thông tin đăng nhập ↓";
    }
  };
  const bulkButton=el.querySelector("#bulk-create-roster");
  if(bulkButton)bulkButton.onclick=async()=>{
    const requiredPhrase="CAP LAI MAT KHAU TOAN LOP";
    if(!confirm("Thao tác này sẽ tạo các tài khoản lớp 12A1 còn thiếu rồi xuất file Excel có mật khẩu hiện đang sử dụng. Những tài khoản đã có bản sao mã hóa hợp lệ sẽ giữ nguyên mật khẩu; tài khoản chưa có bản sao mới được cấp mật khẩu tạm một lần. Các lần xuất sau không đổi mật khẩu. Bạn có muốn tiếp tục?"))return;
    const confirmation=window.prompt('Để xác nhận xuất lại thông tin đăng nhập, hãy nhập chính xác: '+requiredPhrase);
    if(confirmation!==requiredPhrase){
      if(confirmation!==null)toast("Nội dung xác nhận không chính xác. Chưa có mật khẩu nào bị thay đổi.");
      return;
    }
    bulkButton.disabled=true;
    bulkButton.textContent="Đang tạo tài khoản và chuẩn bị file đăng nhập...";
    let created=0,provisionedPasswordReset=0;
    try{
      // Tạo các tài khoản còn thiếu ở cả bốn tổ trước khi cấp mật khẩu mới.
      for(let groupNo=1;groupNo<=4;groupNo++){
        const result=await api("/api/accounts/bulk-create-roster","POST",{group_no:groupNo});
        created+=Number(result.created_count||0);
        provisionedPasswordReset+=Number(result.password_reset_count||0);
      }

      // Endpoint xuất lại mật khẩu từ kho mã hóa; chỉ cấp mới cho tài khoản chưa có
      // bản sao hợp lệ, còn các mật khẩu đã lưu sẽ được giữ nguyên.
      const response=await fetch("/api/accounts/reset-all-student-passwords",{
        method:"POST",
        credentials:"same-origin",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({confirmation:"CAP_LAI_MAT_KHAU_TOAN_LOP"})
      });
      if(!response.ok){
        let message="Không thể tạo tài khoản hoặc xuất file thông tin đăng nhập.";
        try{const data=await response.json();message=data.error||message}catch{}
        throw Error(message);
      }

      const workbook=await response.blob();
      const fileUrl=URL.createObjectURL(workbook);
      const link=document.createElement("a");
      const disposition=response.headers.get("Content-Disposition")||"";
      const filenameMatch=disposition.match(/filename="?([^";]+)"?/i);
      link.href=fileUrl;
      link.download=filenameMatch?filenameMatch[1]:"tai-khoan-dang-nhap-12A1.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(()=>URL.revokeObjectURL(fileUrl),1500);

      const resetCount=Number(response.headers.get("X-Password-Reset-Count")||0);
      const credentialCount=Number(response.headers.get("X-Credential-Count")||0);
      const totalNewPasswords=provisionedPasswordReset+resetCount;
      const auditWarning=response.headers.get("X-Audit-Recorded")==="false"?" Lưu ý: nhật ký quản trị chưa ghi được thao tác xuất file.":"";
      const rosterWarning=credentialCount<47?" File có "+credentialCount+" tài khoản đang hoạt động và đã được duyệt; tài khoản chờ duyệt hoặc đã khóa không được cấp thông tin đăng nhập.":"";
      toast("Đã tạo "+created+" tài khoản còn thiếu; xuất mật khẩu cho "+credentialCount+" tài khoản. Chỉ "+totalNewPasswords+" tài khoản chưa có bản sao được cấp mật khẩu mới; những tài khoản khác giữ nguyên mật khẩu."+rosterWarning+auditWarning);
      await dashboard();
    }catch(error){
      toast(error.message+" Các tài khoản đã tạo trước thời điểm xảy ra lỗi vẫn được giữ nguyên; hãy kiểm tra danh sách trước khi thử lại.");
      bulkButton.disabled=false;
      bulkButton.textContent="Tạo / đồng bộ 47 tài khoản và tải lại file đăng nhập ↓";
    }
  };
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

async function assignmentsPanel(el){
  el.innerHTML='<section class="card"><p class="muted">Đang tải danh sách phân công...</p></section>';
  try{
    const [accountData,dashboardData]=await Promise.all([api("/api/accounts"),api("/api/dashboard")]);
    const allAccounts=accountData.accounts||[];
    const groups=dashboardData.groups||[];
    const candidates=allAccounts.filter(x=>x.role==="member"&&x.is_active&&x.registration_status==="approved");
    const leaderCards=groups.map(group=>{
      const options=candidates.filter(x=>Number(x.group_no)===Number(group.group_no));
      const current=group.leader?'<strong>'+esc(group.leader.full_name)+'</strong>':'<span class="muted">Chưa phân công Tổ trưởng</span>';
      return '<section class="card assignment-card"><div class="assignment-heading"><span class="group-symbol">T'+group.group_no+'</span><div><p class="eyebrow">PHÂN CÔNG TỔ '+group.group_no+'</p><h3>Tổ '+group.group_no+'</h3></div></div><div class="assignment-current"><span>Tổ trưởng hiện tại</span>'+current+'</div><form class="form leader-assignment-form" data-group-no="'+group.group_no+'"><label class="field">Chọn thành viên bổ nhiệm<select name="member_id" required><option value="">Chọn học sinh thuộc Tổ '+group.group_no+'</option>'+options.map(x=>'<option value="'+x.id+'">'+esc(x.full_name)+'</option>').join("")+'</select></label><button class="btn" type="submit" '+(options.length?"":"disabled")+'>'+(group.leader?"Thay đổi Tổ trưởng":"Bổ nhiệm Tổ trưởng")+' <span aria-hidden="true">→</span></button><small class="muted">Tổ trưởng cũ sẽ tự động trở lại vai trò Thành viên trong tổ.</small></form></section>';
    }).join("");

    const selectable=[];
    const seen=new Set();
    for(const group of groups){
      if(group.leader){
        const key="id:"+group.leader.id;
        if(!seen.has(key)){seen.add(key);selectable.push({id:group.leader.id,full_name:group.leader.full_name,group_no:group.group_no,status_label:"Tổ trưởng"})}
      }
      for(const person of (group.members||[])){
        const key=person.id?"id:"+person.id:"name:"+person.full_name;
        if(!seen.has(key)){
          seen.add(key);
          selectable.push({...person,group_no:group.group_no});
        }
      }
    }
    selectable.sort((a,b)=>Number(a.group_no)-Number(b.group_no)||a.full_name.localeCompare(b.full_name,"vi"));
    const transferOptions=selectable.map(person=>{
      const value=person.id?"id:"+person.id:"name:"+encodeURIComponent(person.full_name);
      const label=person.full_name+" · Tổ "+person.group_no+(person.status_label?" · "+person.status_label:"");
      return '<option value="'+esc(value)+'">'+esc(label)+'</option>';
    }).join("");

    el.innerHTML=
      '<div class="assignment-intro"><strong>Quản lý cơ cấu 4 tổ</strong><p>Chỉ Người sáng lập và Giáo viên chủ nhiệm mới có quyền điều chỉnh. Thao tác phân công và chuyển tổ được ghi vào nhật ký quản trị.</p></div>'+
      '<div class="assignment-grid">'+leaderCards+'</div>'+
      '<section class="card assignment-transfer-card"><div class="section-title"><div><p class="eyebrow">ĐIỀU CHUYỂN HỌC SINH</p><h2>Chuyển thành viên sang tổ khác</h2><p class="muted">Có thể chuyển cả học sinh chưa kích hoạt tài khoản trong danh sách lớp.</p></div></div>'+
      '<form id="transfer-member-form" class="transfer-form"><label class="field">Học sinh<select name="student" required><option value="">Chọn học sinh cần chuyển</option>'+transferOptions+'</select></label><label class="field">Tổ mới<select name="to_group" required><option value="">Chọn tổ đích</option><option value="1">Tổ 1</option><option value="2">Tổ 2</option><option value="3">Tổ 3</option><option value="4">Tổ 4</option></select></label><button class="btn" type="submit" '+(selectable.length?"":"disabled")+'><span aria-hidden="true">⇄</span> Chuyển tổ</button></form></section>';

    el.querySelectorAll(".leader-assignment-form").forEach(form=>form.onsubmit=async event=>{
      event.preventDefault();
      const groupNo=Number(form.dataset.groupNo);
      const memberId=Number(new FormData(form).get("member_id"));
      const selected=form.querySelector("select option:checked")?.textContent||"học sinh này";
      if(!confirm('Bổ nhiệm "'+selected+'" làm Tổ trưởng Tổ '+groupNo+'? Tổ trưởng hiện tại sẽ trở lại vai trò Thành viên.'))return;
      try{
        await api("/api/class/assign-leader","POST",{group_no:groupNo,member_id:memberId});
        toast("Đã cập nhật Tổ trưởng Tổ "+groupNo+".");
        await dashboard();
      }catch(error){toast(error.message)}
    });
    const transferForm=el.querySelector("#transfer-member-form");
    if(transferForm)transferForm.onsubmit=async event=>{
      event.preventDefault();
      const values=fd(transferForm);
      const target=Number(values.to_group);
      const selection=String(values.student||"");
      if(!selection)return;
      const payload={to_group:target};
      let displayName="";
      if(selection.startsWith("id:")){
        const id=Number(selection.slice(3));
        payload.member_id=id;
        displayName=selectable.find(x=>Number(x.id)===id)?.full_name||"học sinh";
      }else if(selection.startsWith("name:")){
        displayName=decodeURIComponent(selection.slice(5));
        payload.full_name=displayName;
      }else return;
      if(!confirm('Chuyển "'+displayName+'" sang Tổ '+target+'? Điểm số và nhận xét đã ghi sẽ được giữ nguyên.'))return;
      try{
        const result=await api("/api/class/transfer-member","POST",payload);
        toast(result.message||"Đã chuyển tổ.");
        await dashboard();
      }catch(error){toast(error.message)}
    };
  }catch(error){
    el.innerHTML='<section class="card error-card">'+esc(error.message)+'</section>';
  }
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
