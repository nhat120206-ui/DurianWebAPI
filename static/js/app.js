const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const state = {
  user: null,
  credentials: null,
  selectedFile: null,
  history: [],
  diseases: [],
  lastResult: null,
  cameraStream: null,
  modelAvailable: false,
  modelStatusMessage: "Đang kiểm tra trạng thái mô hình AI..."
};
const API = "";
function toast(msg){const el=$("#toast");el.textContent=msg;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),2600)}
function message(el,msg,error=false){el.textContent=msg;el.className="message"+(error?" error":"")}
async function request(url, options={}) {
  const headers = new Headers(options.headers || {});
  // HTTP Basic: gửi email/mật khẩu trên từng request, chỉ giữ trong bộ nhớ khi đang đăng nhập.
  if (state.credentials) {
    headers.set("Authorization", "Basic " + btoa(unescape(encodeURIComponent(`${state.credentials.email}:${state.credentials.password}`))));
  }
  const res=await fetch(API+url,{...options,headers,credentials:"omit"});
  let data={}; try{data=await res.json()}catch{}
  if(!res.ok) throw new Error(data.detail||data.message||`Lỗi HTTP ${res.status}`);
  return data;
}
function formData(form){return new FormData(form)}
function showAuth(which="login"){
  $("#auth-screen").classList.remove("hidden");$("#app-shell").classList.add("hidden");
  $("#login-form").classList.toggle("hidden",which!=="login");$("#register-form").classList.toggle("hidden",which!=="register");
}

function applyModelGateUI() {
  const locked = !state.modelAvailable;
  const isUser = state.user?.role !== "Admin";
  $$('[data-page="diagnose"]').forEach(el => {
    const shouldLock = locked && isUser;
    el.classList.toggle("is-disabled", shouldLock);
    el.setAttribute("aria-disabled", shouldLock ? "true" : "false");
    el.title = shouldLock ? (state.modelStatusMessage || "Hệ thống chưa có mô hình AI hoạt động.") : "";
  });
}

async function refreshModelStatus() {
  try {
    const status = await request("/api/model-status");
    state.modelAvailable = Boolean(status.available);
    state.modelStatusMessage = status.message || (state.modelAvailable ? "Mô hình sẵn sàng." : "Chưa có mô hình AI hoạt động.");
  } catch (err) {
    state.modelAvailable = false;
    state.modelStatusMessage = err.message || "Không thể kiểm tra trạng thái mô hình AI.";
  }
  applyModelGateUI();
  return state.modelAvailable;
}

async function enterApp(user){
  state.user=user;
  $("#auth-screen").classList.add("hidden");$("#app-shell").classList.remove("hidden");
  $("#user-name").textContent=user.full_name||"Người dùng";$("#welcome-name").textContent=(user.full_name||"bạn").split(" ").slice(-1)[0];
  $("#current-user-role").textContent = user.role === "Admin" ? "Quản trị viên" : "Thành viên";
  $("#user-avatar").textContent=(user.full_name||"U").trim().charAt(0).toUpperCase();
  $("#profile-avatar").textContent=$("#user-avatar").textContent;$("#profile-name").textContent=user.full_name||"Người dùng";
  $("#profile-email").textContent=user.email||"";$("#profile-email-input").value=user.email||"";
  $("#profile-fullname").value=user.full_name||"";$("#profile-role").textContent=user.role==="Admin"?"Quản trị viên":"Thành viên";
  $("#admin-nav").classList.toggle("hidden",user.role!=="Admin");
  $("#today-label").textContent=new Date().toLocaleDateString("vi-VN",{weekday:"long",day:"2-digit",month:"long",year:"numeric"});

  const ready = await refreshModelStatus();
  if (!ready) {
    if (user.role === "Admin") {
      navigate("models");
      message($("#model-message"), state.modelStatusMessage + " Vui lòng tải lên và kích hoạt mô hình.", true);
      toast("Chưa có mô hình AI hoạt động. Vui lòng thêm và kích hoạt mô hình.");
      return;
    }
    toast("Chức năng chẩn đoán tạm khóa do hệ thống chưa có mô hình AI.");
  }
  navigate("dashboard");
}

let currentPage = null;
function resetTransientPage(page){
  if(!page) return;
  if(page==="diagnose"){
    state.selectedFile=null;
    state.lastResult=null;
    const imageInput=$("#image-input");
    if(imageInput) imageInput.value="";
    const preview=$("#preview-wrap"), dropzone=$("#dropzone"), run=$("#run-diagnosis");
    if(preview) preview.classList.add("hidden");
    if(dropzone) dropzone.classList.remove("hidden");
    if(run){run.disabled=true;run.textContent="Phân tích bằng AI →";}
    const result=$("#diagnosis-result");
    if(result) result.innerHTML='<div class="result-placeholder"><div class="result-graphic">✦</div><b>Kết quả chẩn đoán sẽ hiển thị tại đây</b><p>Tải ảnh lên để bắt đầu phân tích.</p></div>';
    const msg=$("#diagnose-message"); if(msg) message(msg,"");
    if(state.cameraStream) state.cameraStream.getTracks().forEach(t=>t.stop());
    state.cameraStream=null;
    const cameraModal=$("#camera-modal"); if(cameraModal) cameraModal.classList.add("hidden");
  }
  const resetMap = {
  "manage-diseases": ["#admin-disease-form"],
  "treatments": ["#treatment-form"],
  "models": ["#model-form", "#training-data-form"],
  "users": ["#user-form"],
  "profile": ["#password-form"]
};
  (resetMap[page]||[]).forEach(selector=>{
    const form=$(selector); if(form) form.reset();
  });
  if(page==="manage-diseases"){
    const title=$("#disease-form-title"); if(title) title.textContent="Thêm bệnh mới";
    const msg=$("#admin-disease-message"); if(msg) message(msg,"");
  }
  if(page==="treatments"){const msg=$("#treatment-message");if(msg)message(msg,"");}
  if(page==="models"){const msg=$("#model-message");if(msg)message(msg,"");}
  if (page === "models") {
  const msg = $("#model-message"); if (msg) message(msg, "");
  const tdModal = $("#training-data-modal"); if (tdModal) tdModal.classList.add("hidden");
}
if (page === "profile") {
  const msg = $("#profile-message"); if (msg) message(msg, "");
}
  if(page==="users"){
    const modal=$("#user-modal"); if(modal) modal.classList.add("hidden");
    const role=$("#user-role");
    if(role) role.disabled=false;
  }
}

function navigate(page){
  const adminPages=["stats","users","manage-diseases","treatments","models"];
  if(adminPages.includes(page) && state.user?.role!=="Admin"){
    toast("Bạn không có quyền truy cập chức năng quản trị.");
    page="dashboard";
  }
  if(!state.user){showAuth("login");return;}

  // Chặn trang chẩn đoán khi chưa có model hoạt động
  if(page==="diagnose" && !state.modelAvailable){
    if(state.user.role==="Admin"){
      toast("Chưa có mô hình AI hoạt động. Vui lòng thêm hoặc kích hoạt mô hình.");
      page="models";
    } else {
      toast(state.modelStatusMessage || "Hệ thống chưa có mô hình AI, tạm thời không thể chẩn đoán.");
      page="dashboard";
    }
  }

  if(currentPage && currentPage!==page) resetTransientPage(currentPage);
  currentPage=page;
  $$(".page").forEach(p=>p.classList.toggle("active",p.id===`page-${page}`));
  $$(".nav-item[data-page]").forEach(b=>b.classList.toggle("active",b.dataset.page===page));
  const active=$(`[data-page="${page}"]`);$("#crumb").textContent=active?active.textContent.trim():"Tổng quan";
  $("#sidebar").classList.remove("open");
  const loaders={dashboard:loadDashboard,loadProfile,history:loadHistory,diseases:loadDiseases,stats:loadStats,users:loadUsers,"manage-diseases":loadAdminDiseases,treatments:loadTreatments,models:loadModels,profile: loadProfile};
  if(loaders[page])loaders[page]();
}
function safe(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function statusBadge(s){let cls=s==="Failed"?"failed":s==="Pending"?"pending":"";let label=s==="Completed"?"Hoàn thành":s==="Failed"?"Thất bại":s==="Pending"?"Đang xử lý":s||"—";return `<span class="status ${cls}">${label}</span>`}
async function loadDashboard(){
  if(!state.user)return;
  try{
    const [hist,diseases]=await Promise.all([request(`/api/history/${state.user.user_id}`),request("/api/diseases")]);
    state.history=hist;state.diseases=diseases;
    $("#stat-total").textContent=hist.length;$("#stat-diseases").textContent=diseases.length;
    const latest=hist[0];$("#stat-last").textContent=latest?latest.top1_confidence+"%":"—";$("#stat-last-date").textContent=latest?latest.diagnosis_date:"Chưa có dữ liệu";
    $("#recent-list").innerHTML=hist.slice(0,4).map(x=>`<div class="recent-row"><img src="${safe(x.image_path)}" onerror="this.style.visibility='hidden'"><div><b>${safe(x.top1_disease||"Chưa có kết quả")}</b><small>${safe(x.diagnosis_date)} · ${safe(x.status)}</small></div><span class="confidence">${Number(x.top1_confidence||0).toFixed(1)}%</span></div>`).join("")||'<div class="empty-state">Chưa có lần chẩn đoán nào.</div>';
  }catch(e){toast(e.message)}
}
function loadProfile() {
  if (!state.user) return;
  const profileForm = $("#profile-form");
  const passwordForm = $("#password-form");
  if (profileForm) profileForm.reset();
  if (passwordForm) passwordForm.reset();
  $("#profile-fullname").value = state.user.full_name || "";
  $("#profile-email-input").value = state.user.email || "";
  $("#profile-name").textContent = state.user.full_name || "Người dùng";
  $("#profile-email").textContent = state.user.email || "";
  $("#profile-role").textContent = state.user.role === "Admin" ? "Quản trị viên" : "Thành viên";
  const msg = $("#profile-message");
  if (msg) message(msg, "");
}
function setSelectedFile(file){
  if(!file)return;
  if(!["image/jpeg","image/png","image/webp"].includes(file.type)){toast("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.");return}
  state.selectedFile=file;$("#image-preview").src=URL.createObjectURL(file);$("#file-name").textContent=file.name;$("#file-size").textContent=(file.size/1024/1024).toFixed(2)+" MB";
  $("#preview-wrap").classList.remove("hidden");$("#dropzone").classList.add("hidden");$("#run-diagnosis").disabled=false;$("#diagnosis-result").innerHTML='<div class="result-placeholder"><div class="result-graphic">✦</div><b>Ảnh đã sẵn sàng</b><p>Nhấn phân tích để nhận kết quả.</p></div>';
}
async function runDiagnosis(){
  if(!state.selectedFile||!state.user)return;
  if(!state.modelAvailable){
    const msg = state.modelStatusMessage || "Hệ thống chưa có mô hình AI hoạt động.";
    message($("#diagnose-message"), msg, true);
    toast(msg);
    return;
  }
  const btn=$("#run-diagnosis");btn.disabled=true;btn.textContent="Đang phân tích...";
  message($("#diagnose-message"),"Đang tải ảnh và chờ mô hình AI xử lý...");
  const fd=new FormData();fd.append("user_id",state.user.user_id);fd.append("file",state.selectedFile);
  try{
    const r=await request("/api/diagnose",{method:"POST",body:fd});state.lastResult=r;renderDiagnosis(r);
    message($("#diagnose-message"),"Phân tích hoàn tất.");toast("Đã nhận kết quả chẩn đoán.");
  }catch(e){message($("#diagnose-message"),e.message,true);$("#diagnosis-result").innerHTML=`<div class="result-placeholder"><b>Không thể hoàn tất chẩn đoán</b><p>${safe(e.message)}</p></div>`}
  finally{btn.disabled=false;btn.textContent="Phân tích bằng AI →"}
}
function renderDiagnosis(r){
  const top=(r.top3||[]).map((x,i)=>`<div class="prediction"><div class="prediction-top"><b>${i+1}. ${safe(x.disease_name)}</b><strong>${Number(x.confidence_percent).toFixed(2)}%</strong></div><div class="progress"><span style="width:${Math.max(0,Math.min(100,x.confidence_percent))}%"></span></div><div class="treatment-mini"><b>Triệu chứng:</b> ${safe(x.symptoms||"Chưa có thông tin")}<br><b>Mô tả:</b> ${safe(x.description||"Chưa có mô tả")}${(x.treatments||[]).map(t=>`<br><b>${safe(t.treatment_name)}:</b> ${safe(t.description||"")}`).join("")}</div></div>`).join("");
  $("#diagnosis-result").innerHTML=`${r.is_uncertain?'<div class="result-alert">⚠ Kết quả chưa chắc chắn. Ảnh có thể chưa rõ hoặc nằm ngoài nhóm dữ liệu mô hình đã học.</div>':""}<img class="result-photo" src="${safe(r.image_path)}" alt="Ảnh chẩn đoán"><div class="panel-heading"><div><h3>Kết quả dự đoán Top 3</h3><p class="muted">${safe(r.model_used||"Mô hình AI")} · ${safe(r.processing_time_ms||"—")} ms</p></div><span class="status">${safe(r.status)}</span></div>${top||'<p>Không có kết quả dự đoán.</p>'}<div class="feedback-row"><button class="btn btn-outline" id="feedback-yes">✓ Kết quả đúng</button><button class="btn btn-outline" id="feedback-no">✕ Kết quả sai</button></div><div id="feedback-form" class="hidden"><label class="muted">Nếu biết, chọn bệnh thực tế<select id="actual-disease" class="search-input"><option value="">Chưa xác định</option>${state.diseases.map(d=>`<option value="${d.disease_id}">${safe(d.disease_name)}</option>`).join("")}</select></label><button class="btn btn-primary" id="send-feedback">Gửi phản hồi</button></div>`;
  $("#feedback-yes").onclick=()=>sendFeedback(true,null,r.diagnosis_id);
  $("#feedback-no").onclick=()=>$("#feedback-form").classList.remove("hidden");
  $("#send-feedback").onclick=()=>sendFeedback(false,$("#actual-disease").value||null,r.diagnosis_id);
}
async function sendFeedback(correct,actual,id){const fd=new FormData();fd.append("is_correct",correct);if(actual)fd.append("actual_disease_id",actual);try{await request(`/api/diagnose/${id}/feedback`,{method:"POST",body:fd});toast("Cảm ơn bạn đã gửi phản hồi.");$("#feedback-form").classList.add("hidden")}catch(e){toast(e.message)}}
async function loadHistory(){
  try{state.history=await request(`/api/history/${state.user.user_id}`);renderHistory(state.history)}catch(e){$("#history-body").innerHTML=`<tr><td colspan="6">${safe(e.message)}</td></tr>`}
}
function renderHistory(rows){
  $("#history-body").innerHTML=rows.map(r=>`<tr><td><img class="table-thumb" src="${safe(r.image_path)}" onerror="this.style.visibility='hidden'"></td><td>${safe(r.diagnosis_date)}</td><td><b>${safe(r.top1_disease||"—")}</b></td><td>${Number(r.top1_confidence||0).toFixed(2)}%</td><td>${statusBadge(r.status)}${r.is_uncertain?' <span class="status pending">Chưa chắc chắn</span>':""}</td><td><button class="mini-btn danger" data-delete-history="${r.diagnosis_id}">Xóa</button></td></tr>`).join("")||'<tr><td colspan="6" class="empty-cell">Bạn chưa có lịch sử chẩn đoán.</td></tr>';
  $$("[data-delete-history]").forEach(b=>b.onclick=async()=>{if(!confirm("Bạn có chắc muốn xóa lần chẩn đoán này?"))return;try{await request(`/api/history/${b.dataset.deleteHistory}`,{method:"DELETE"});toast("Đã xóa lịch sử.");loadHistory()}catch(e){toast(e.message)}});
}
async function loadDiseases(){
  try{state.diseases=await request("/api/diseases");renderDiseases(state.diseases)}catch(e){$("#disease-grid").textContent=e.message}
}
function renderDiseases(rows){
  $("#disease-count").textContent=`${rows.length} bệnh`;
  $("#disease-grid").innerHTML=rows.map(d=>`<article class="disease-card"><div class="disease-symbol">❀</div><h3>${safe(d.disease_name)}</h3><p>${safe(d.description||d.symptoms||"Chưa có mô tả.")}</p><details><summary>Xem triệu chứng & biện pháp</summary><p><b>Triệu chứng:</b> ${safe(d.symptoms||"Chưa cập nhật")}</p>${(d.treatments||[]).map(t=>`<p><b>${safe(t.treatment_name)}</b> (${safe(t.treatment_type)})<br>${safe(t.description||"")}<br><b>Phòng ngừa:</b> ${safe(t.prevention||"Chưa cập nhật")}</p>`).join("")||"<p>Chưa có biện pháp cho bệnh này.</p>"}</details></article>`).join("")||'<div class="empty-state">Không tìm thấy bệnh phù hợp.</div>';
}
async function loadStats(){try{const s=await request("/api/admin/stats");$("#admin-total").textContent=s.total_diagnoses;$("#admin-uncertain").textContent=s.uncertain_count;$("#admin-failed").textContent=s.failed_count;$("#admin-feedback").textContent=`${s.correct_feedback} / ${s.wrong_feedback}`;$("#wrong-cases").innerHTML=(s.wrong_cases||[]).map(x=>`<tr><td>#${x.diagnosis_id}</td><td>${safe(x.date)}</td><td><img class="table-thumb" src="${safe(x.image_path)}"></td><td>${safe(x.actual_disease)}</td></tr>`).join("")||'<tr><td colspan="4" class="empty-cell">Chưa có phản hồi sai.</td></tr>'}catch(e){toast(e.message)}}
async function loadUsers(){
  try{
    const rows=await request("/api/admin/users");
    $("#users-body").innerHTML=rows.map(u=>`<tr>
      <td><b>${safe(u.full_name)}</b></td><td>${safe(u.email)}</td><td>${safe(u.role)}</td><td>${safe(u.created_at)}</td>
      <td><span class="status ${u.is_active?"":"failed"}">${u.is_active?"Hoạt động":"Đã khóa"}</span></td>
      <td class="user-actions"><button class="mini-btn" data-edit-user="${u.user_id}">Sửa</button><button class="mini-btn ${u.is_active?"danger":""}" data-toggle-user="${u.user_id}" ${u.user_id===state.user.user_id?"disabled title=\"Không thể khóa tài khoản đang đăng nhập\"":""}>${u.is_active?"Khóa":"Mở khóa"}</button></td>
    </tr>`).join("")||'<tr><td colspan="6" class="empty-cell">Chưa có người dùng.</td></tr>';
    $$('[data-toggle-user]').forEach(b=>b.onclick=async()=>{
      const fd=new FormData();fd.append("current_admin_id",state.user.user_id);
      try{await request(`/api/admin/users/${b.dataset.toggleUser}/toggle-lock`,{method:"POST",body:fd});toast("Đã cập nhật tài khoản.");loadUsers()}catch(e){toast(e.message)}
    });
    $$('[data-edit-user]').forEach(b=>b.onclick=()=>{const user=rows.find(u=>u.user_id===Number(b.dataset.editUser));openUserModal("edit",user)});
  }catch(e){toast(e.message)}
}

function openUserModal(mode = "create", user = null) {
  const form = $("#user-form");
  const roleSelect = form.elements.namedItem("role");
  const nameInput = form.elements.namedItem("full_name");
  const emailInput = form.elements.namedItem("email");

  if (!form || !nameInput || !emailInput || !roleSelect) {
    console.error("Không tìm thấy các trường trong user-form.");
    return;
  }

  form.reset();
  $("#user-form-message").textContent = "";

  const editing = mode === "edit";

  $("#user-modal-title").textContent = editing ? "Sửa thông tin người dùng" : "Thêm người dùng mới";
  $("#save-user-btn").textContent = editing ? "Lưu thay đổi" : "Thêm người dùng";
  $("#edit-user-id").value = editing ? user.user_id : "";

  nameInput.value = editing ? (user.full_name || "") : "";
  emailInput.value = editing ? (user.email || "") : "";
  nameInput.disabled = false;
  nameInput.readOnly = false;
  emailInput.disabled = false;
  emailInput.readOnly = false;

  roleSelect.value = editing ? user.role : "User";

  $("#user-password").required = !editing;
  $("#user-password").value = "";
  $("#user-password").placeholder = editing ? "Để trống nếu không đổi mật khẩu" : "Ít nhất 6 ký tự";
  $("#password-hint").textContent = editing ? "(để trống nếu không đổi)" : "(bắt buộc khi thêm mới)";

  roleSelect.disabled = editing && Number(user.user_id) === Number(state.user.user_id);

  $("#user-modal").classList.remove("hidden");
  nameInput.focus();
}

function closeUserModal() {
  $("#user-modal").classList.add("hidden");
  const roleSelect = $("#user-form").elements.namedItem("role");
  if (roleSelect) roleSelect.disabled = false;
}

async function loadAdminDiseases(){
  try{state.diseases=await request("/api/diseases");$("#admin-disease-list").innerHTML=state.diseases.map(d=>`<div class="admin-list-item"><div><b>${safe(d.disease_name)}</b><small>ID: ${d.disease_id}</small></div><button class="mini-btn" data-edit-disease="${d.disease_id}">Chỉnh sửa</button></div>`).join("")||"Chưa có bệnh";$("#treatment-disease").innerHTML=state.diseases.map(d=>`<option value="${d.disease_id}">${safe(d.disease_name)}</option>`).join("");$$("[data-edit-disease]").forEach(b=>b.onclick=()=>{const d=state.diseases.find(x=>x.disease_id==b.dataset.editDisease);const f=$("#admin-disease-form");f.elements.disease_id.value=d.disease_id;f.elements.disease_name.value=d.disease_name;f.elements.symptoms.value=d.symptoms||"";f.elements.description.value=d.description||"";$("#disease-form-title").textContent="Cập nhật bệnh"})}catch(e){toast(e.message)}
}
async function loadTreatments(){try{state.diseases=await request("/api/diseases");$("#treatment-disease").innerHTML=state.diseases.map(d=>`<option value="${d.disease_id}">${safe(d.disease_name)}</option>`).join("");const all=state.diseases.flatMap(d=>(d.treatments||[]).map(t=>({...t,disease_name:d.disease_name})));$("#treatment-list").innerHTML=all.map(t=>`<div class="admin-list-item"><div><b>${safe(t.treatment_name)}</b><small>${safe(t.disease_name)} · ${safe(t.treatment_type)}</small></div><button class="mini-btn danger" data-delete-treatment="${t.treatment_id}">Xóa</button></div>`).join("")||"Chưa có biện pháp";$$("[data-delete-treatment]").forEach(b=>b.onclick=async()=>{if(!confirm("Xóa biện pháp này?"))return;try{await request(`/api/admin/treatments/${b.dataset.deleteTreatment}`,{method:"DELETE"});toast("Đã xóa biện pháp.");loadTreatments()}catch(e){toast(e.message)}})}catch(e){toast(e.message)}}
async function loadModels() {
  try {
    const rows = await request("/api/admin/models");
    $("#model-list").innerHTML = rows.map(m => {
      const td = m.training_data
        ? ` · Dữ liệu: ${safe(m.training_data.file_format)}${m.training_data.source ? " (" + safe(m.training_data.source) + ")" : ""}`
        : "";
      return `<div class="admin-list-item"><div><b>${safe(m.model_name)} ${safe(m.version)}</b><small>Accuracy: ${Number(m.accuracy || 0).toFixed(3)} · F1: ${Number(m.f1_score || 0).toFixed(3)}${td} ${m.is_active ? "· Đang hoạt động" : ""}</small></div>${m.is_active ? '<span class="status">Đang dùng</span>' : `<button class="mini-btn" data-activate-model="${m.model_id}">Kích hoạt</button>`}</div>`;
    }).join("") || "Chưa có phiên bản";

    $$("[data-activate-model]").forEach(b => b.onclick = async () => {
      if (!confirm("Kích hoạt phiên bản mô hình này?")) return;
      try {
        await request(`/api/admin/models/${b.dataset.activateModel}/activate`, { method: "POST" });
        await refreshModelStatus();
        message($("#model-message"), "Đã kích hoạt mô hình. Chức năng chẩn đoán đã sẵn sàng.");
        toast("Đã kích hoạt mô hình.");
        loadModels();
      } catch (e) { toast(e.message); }
    });
  } catch (e) { toast(e.message); }
}

$("#show-register").onclick=()=>showAuth("register");
$("#show-login").onclick=()=>showAuth("login");

$("#login-form").onsubmit=async e=>{
  e.preventDefault();
  const submit=e.target.querySelector('button[type="submit"]');
  submit.disabled=true;
  try{
    const loginData=new FormData(e.target);
    const user=await request("/api/auth/login",{method:"POST",body:loginData});
    state.credentials={email:loginData.get("email"),password:loginData.get("password")};
    e.target.reset();
    message($("#auth-message"),"");
    await enterApp(user);
    toast("Đăng nhập thành công.");
  }catch(err){message($("#auth-message"),err.message,true)}
  finally{submit.disabled=false}
};
$("#register-form").onsubmit=async e=>{
  e.preventDefault();
  const submit=e.target.querySelector('button[type="submit"]');
  submit.disabled=true;
  try{
    const result=await request("/api/auth/register",{method:"POST",body:formData(e.target)});
    e.target.reset();
    showAuth("login");
    message($("#auth-message"),result.message);
  }catch(err){message($("#register-message"),err.message,true)}
  finally{submit.disabled=false}
};

function logout(){
  if(state.cameraStream) state.cameraStream.getTracks().forEach(t=>t.stop());
  state.cameraStream=null;
  state.user=null;
  state.credentials=null;
  state.selectedFile=null;
  state.history=[];
  state.diseases=[];
  state.modelAvailable=false;
  state.modelStatusMessage="Đang kiểm tra trạng thái mô hình AI...";
  currentPage=null;
  showAuth("login");
  message($("#auth-message"),"Bạn đã đăng xuất.");
}
$("#logout-btn").onclick=logout;
$("#main-nav").onclick=e=>{const b=e.target.closest("[data-page]");if(b)navigate(b.dataset.page)};
$("#admin-nav").onclick=e=>{const b=e.target.closest("[data-page]");if(b)navigate(b.dataset.page)};
$$("[data-page]").forEach(b=>b.addEventListener("click",()=>navigate(b.dataset.page)));
$("#mobile-menu").onclick=()=>$("#sidebar").classList.toggle("open");
$("#choose-image").onclick=()=>$("#image-input").click();
async function closeCamera(){
  if(state.cameraStream){state.cameraStream.getTracks().forEach(t=>t.stop());state.cameraStream=null;}
  $("#camera-video").srcObject=null;$("#camera-modal").classList.add("hidden");
}
$("#open-camera").onclick=async()=>{
  $("#camera-modal").classList.remove("hidden");message($("#camera-error"),"");
  try{
    if(!navigator.mediaDevices?.getUserMedia) throw new Error("Trình duyệt không hỗ trợ camera hoặc trang chưa chạy trên localhost/HTTPS.");
    state.cameraStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"},audio:false});
    $("#camera-video").srcObject=state.cameraStream;
  }catch(err){message($("#camera-error"),err.message,true)}
};
$("#close-camera").onclick=closeCamera;
$("#camera-modal").onclick=e=>{if(e.target.id==="camera-modal")closeCamera()};
$("#capture-photo").onclick=()=>{
  const video=$("#camera-video"),canvas=$("#camera-canvas");
  if(!video.videoWidth){message($("#camera-error"),"Camera chưa sẵn sàng.",true);return}
  canvas.width=video.videoWidth;canvas.height=video.videoHeight;
  canvas.getContext("2d").drawImage(video,0,0);
  canvas.toBlob(blob=>{if(blob){setSelectedFile(new File([blob],"durian-camera.jpg",{type:"image/jpeg"}));closeCamera()}}, "image/jpeg", .92);
};
$("#image-input").onchange=e=>setSelectedFile(e.target.files[0]);
$("#remove-image").onclick=()=>{state.selectedFile=null;$("#image-input").value="";$("#preview-wrap").classList.add("hidden");$("#dropzone").classList.remove("hidden");$("#run-diagnosis").disabled=true};
$("#run-diagnosis").onclick=runDiagnosis;
$("#dropzone").ondragover=e=>{e.preventDefault();$("#dropzone").classList.add("dragging")};
$("#dropzone").ondragleave=()=>$("#dropzone").classList.remove("dragging");
$("#dropzone").ondrop=e=>{e.preventDefault();$("#dropzone").classList.remove("dragging");setSelectedFile(e.dataTransfer.files[0])};
$("#history-search").oninput=e=>{const q=e.target.value.toLowerCase();renderHistory(state.history.filter(x=>(x.top1_disease||"").toLowerCase().includes(q)))};
$("#disease-search").oninput=e=>{const q=e.target.value.toLowerCase();renderDiseases(state.diseases.filter(d=>d.disease_name.toLowerCase().includes(q)))};
$("#profile-form").onsubmit = async e => {
  e.preventDefault();
  const newName = $("#profile-fullname").value.trim();
  if (!newName) {
    message($("#profile-message"), "Vui lòng nhập họ và tên.", true);
    return;
  }
  const fd = new FormData();
  fd.append("full_name", newName);
  try {
    const r = await request(`/api/profile/${state.user.user_id}`, { method: "PUT", body: fd });
    state.user.full_name = r.full_name || newName;
    $("#user-name").textContent = state.user.full_name;
    $("#welcome-name").textContent = state.user.full_name.split(" ").slice(-1)[0];
    $("#user-avatar").textContent = state.user.full_name.trim().charAt(0).toUpperCase();
    $("#profile-avatar").textContent = $("#user-avatar").textContent;
    $("#profile-name").textContent = state.user.full_name;
    $("#profile-fullname").value = state.user.full_name;
    message($("#profile-message"), r.message);
  } catch (err) {
    message($("#profile-message"), err.message, true);
  }
};
$("#password-form").onsubmit = async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const newPassword = fd.get("new_password");
  try {
    const r = await request(`/api/profile/${state.user.user_id}`, { method: "PUT", body: fd });
    if (state.credentials && newPassword) {
      state.credentials.password = newPassword;
    }
    message($("#profile-message"), r.message);
    e.target.reset();
  } catch (err) {
    message($("#profile-message"), err.message, true);
  }
};
$("#admin-disease-form").onsubmit=async e=>{e.preventDefault();try{const r=await request("/api/admin/diseases",{method:"POST",body:formData(e.target)});message($("#admin-disease-message"),r.message);e.target.reset();$("#disease-form-title").textContent="Thêm bệnh mới";loadAdminDiseases()}catch(err){message($("#admin-disease-message"),err.message,true)}};
$("#treatment-form").onsubmit=async e=>{e.preventDefault();try{const r=await request("/api/admin/treatments",{method:"POST",body:formData(e.target)});message($("#treatment-message"),r.message);e.target.reset();loadTreatments()}catch(err){message($("#treatment-message"),err.message,true)}};
function openTrainingDataModal() {
  const tdForm = $("#training-data-form");
  if (tdForm) tdForm.reset();
  message($("#td-form-message"), "");
  $("#training-data-modal").classList.remove("hidden");
  $("#td-file-format")?.focus();
}

function closeTrainingDataModal() {
  $("#training-data-modal")?.classList.add("hidden");
  message($("#td-form-message"), "");
}

$("#close-td-modal").onclick = closeTrainingDataModal;
$("#cancel-td-modal").onclick = closeTrainingDataModal;
$("#training-data-modal").onclick = e => {
  if (e.target.id === "training-data-modal") closeTrainingDataModal();
};

// Bước 1: Kiểm tra form model -> Mở pop-up nhập DuLieuHuanLuyen
$("#model-form").onsubmit = e => {
  e.preventDefault();
  const file = $("#model-file")?.files?.[0];
  if (!file) { message($("#model-message"), "Vui lòng chọn tệp .pth hoặc .pt.", true); return; }
  if (!/\.(pth|pt)$/i.test(file.name)) { message($("#model-message"), "Chỉ chấp nhận tệp .pth hoặc .pt.", true); return; }
  if (file.size === 0) { message($("#model-message"), "Tệp mô hình đang trống.", true); return; }
  if (file.size > 1024 ** 3) { message($("#model-message"), "Tệp vượt quá giới hạn 1 GB.", true); return; }
  message($("#model-message"), "");
  openTrainingDataModal();
};

// Bước 2: Xác nhận trên pop-up -> Gộp FormData và gọi POST /api/admin/models
$("#training-data-form").onsubmit = async e => {
  e.preventDefault();
  const modelForm = $("#model-form");
  const tdForm = e.target;
  const formatVal = $("#td-file-format").value.trim();
  if (!formatVal) {
    message($("#td-form-message"), "Vui lòng nhập định dạng dữ liệu huấn luyện.", true);
    return;
  }

  const fd = new FormData(modelForm);
  fd.append("file_format", formatVal);
  const sizeVal = $("#td-file-size").value.trim();
  if (sizeVal !== "") fd.append("file_size", sizeVal);
  const srcVal = $("#td-source").value.trim();
  if (srcVal) fd.append("source", srcVal);
  const descVal = $("#td-description").value.trim();
  if (descVal) fd.append("description", descVal);

  const submitBtn = $("#save-td-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "Đang tải lên...";
  try {
    const r = await request("/api/admin/models", { method: "POST", body: fd });
    closeTrainingDataModal();
    modelForm.reset();
    tdForm.reset();
    message($("#model-message"), r.message + (r.file_name ? ` Tệp lưu: ${r.file_name}` : "") + " Hãy bấm Kích hoạt để sử dụng.");
    toast("Đã thêm phiên bản mô hình và dữ liệu huấn luyện.");
    loadModels();
  } catch (err) {
    message($("#td-form-message"), err.message, true);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Xác nhận tải lên & lưu";
  }
};
$("#refresh-stats").onclick=loadStats;
$("#add-user-btn").onclick=()=>openUserModal("create");
$("#close-user-modal").onclick=closeUserModal;
$("#cancel-user-modal").onclick=closeUserModal;
$("#user-modal").onclick=e=>{if(e.target.id==="user-modal")closeUserModal()};
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("#user-modal").classList.contains("hidden"))closeUserModal()});
$("#user-form").onsubmit=async e=>{
  e.preventDefault();
  const editing=Boolean($("#edit-user-id").value);
  const fd=new FormData(e.target);
  const roleSelect = e.target.elements.namedItem("role");
  if (roleSelect?.disabled) {
    fd.set("role", "Admin");
  }
  const url=editing?`/api/admin/users/${$("#edit-user-id").value}`:"/api/admin/users";
  try{
    const result=await request(url,{method:editing?"PUT":"POST",body:fd});
    if(editing&&Number($("#edit-user-id").value)===state.user.user_id){
      state.user.full_name=result.full_name;state.user.email=result.email;state.user.role=result.role;
      if(state.credentials)state.credentials.email=result.email;
      await enterApp(state.user);navigate("users");
    }
    closeUserModal();toast(result.message);loadUsers();
  }catch(err){message($("#user-form-message"),err.message,true)}
};
// Không tự đăng nhập tài khoản khách. Mỗi lần tải lại trang cần đăng nhập lại.
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    if (!$("#user-modal").classList.contains("hidden")) closeUserModal();
    if (!$("#training-data-modal").classList.contains("hidden")) closeTrainingDataModal();
  }
});
showAuth("login");