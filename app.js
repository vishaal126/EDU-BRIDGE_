/* EduBridge AI frontend: plain JS that talks to the Flask API at /api. */
const $app = document.getElementById("app");
let token = localStorage.getItem("eb_token") || "", me = null, tab = "tutors";

/* ---- tiny DOM helper: text is always set via textContent, so user content can't inject HTML ---- */
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "class") n.className = v;
    else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null) n.append(c.nodeType ? c : document.createTextNode(c));
  return n;
}
function toast(msg) {
  const t = document.getElementById("toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 3000);
}

/* ---- API client ---- */
async function api(method, path, data) {
  let res;
  try {
    res = await fetch("api" + path, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: data ? JSON.stringify(data) : undefined });
  } catch { throw new Error("Can't reach the server. Check your connection."); }
  const out = await res.json().catch(() => ({}));
  if (res.status === 401 && token) { signOutLocal(); throw new Error("Please sign in again."); }
  if (!res.ok) throw new Error(out.error || "Request failed.");
  return out;
}
function signOutLocal() { token = ""; me = null; localStorage.removeItem("eb_token"); render(); }
async function run(btn, fn) {           // disable a button while a request runs; show errors as toasts
  btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message); } finally { btn.disabled = false; }
}
const field = (label, input) => el("div", {}, el("label", {}, label), input);

/* ---- auth screen ---- */
function authView() {
  let mode = "login";
  const box = el("div", { class: "auth" });
  const draw = () => {
    const err = el("div", { class: "err", role: "alert" });
    const f = {
      name: el("input", { autocomplete: "name" }), email: el("input", { type: "email", autocomplete: "email" }),
      password: el("input", { type: "password", autocomplete: mode === "login" ? "current-password" : "new-password" }),
      role: el("select", {}, el("option", { value: "student" }, "I'm a student"), el("option", { value: "tutor" }, "I'm a tutor")),
      skills: el("input", { placeholder: "e.g. Python, Math" }), city: el("input"),
    };
    const go = el("button", { type: "submit" }, mode === "login" ? "Sign in" : "Create account");
    const form = el("form", { onsubmit: e => { e.preventDefault(); err.textContent = "";
      run(go, async () => {
        try {
          const body = mode === "login" ? { email: f.email.value, password: f.password.value }
            : { name: f.name.value, email: f.email.value, password: f.password.value, role: f.role.value, skills: f.skills.value, city: f.city.value };
          const d = await api("POST", mode === "login" ? "/login" : "/register", body);
          token = d.token; me = d.user; localStorage.setItem("eb_token", token); tab = me.role === "tutor" ? "bookings" : "tutors"; render();
        } catch (x) { err.textContent = x.message; }
      }); } },
      mode === "register" ? [field("Full name", f.name), field("I am a", f.role)] : null,
      field("Email", f.email), field(mode === "login" ? "Password" : "Password (8+ characters)", f.password),
      mode === "register" ? [field("Skills (optional)", f.skills), field("City (optional)", f.city)] : null,
      err, el("div", { class: "row", style: "margin-top:14px" }, go,
        el("button", { type: "button", class: "ghost", onclick: () => { mode = mode === "login" ? "register" : "login"; draw(); } }, mode === "login" ? "Create an account" : "I have an account")));
    box.replaceChildren(el("h1", {}, "🎓 EduBridge AI"), el("p", { class: "muted" }, "Learn from peers and tutors."), el("div", { class: "card" }, form));
  };
  draw(); return box;
}

/* ---- main views ---- */
const TABS = { student: [["tutors", "Find tutors"], ["bookings", "My bookings"], ["doubts", "Doubts"], ["profile", "Profile"]],
               tutor: [["bookings", "Requests"], ["doubts", "Doubts"], ["profile", "Profile"]] };

function shell() {
  const body = el("div", {});
  const nav = el("nav", {}, TABS[me.role].map(([k, label]) => el("button", { class: k === tab ? "on" : "", onclick: () => { tab = k; render(); } }, label)));
  const out = el("main", {}, el("div", { class: "row" }, el("div", { class: "grow" }, el("h1", {}, "🎓 EduBridge AI"), el("span", { class: "muted" }, `${me.name} · ${me.role}`)),
    el("button", { class: "ghost", onclick: e => run(e.target, async () => { try { await api("POST", "/logout"); } catch {} signOutLocal(); }) }, "Sign out")), nav, body);
  views[tab](body); return out;
}

const views = {
  async tutors(root) {
    const list = el("div", {});
    const q = el("input", { type: "search", placeholder: "Search by name, skill or city" });
    const load = async () => {
      const { tutors } = await api("GET", "/tutors?q=" + encodeURIComponent(q.value));
      list.replaceChildren(...(tutors.length ? tutors.map(t => tutorCard(t)) : [el("p", { class: "muted" }, "No tutors found yet.")]));
    };
    let timer; q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load().catch(e => toast(e.message)), 250); });
    root.append(q, list); load().catch(e => toast(e.message));
  },
  async bookings(root) {
    const { bookings } = await api("GET", "/bookings").catch(e => (toast(e.message), { bookings: [] }));
    root.append(el("h2", {}, me.role === "tutor" ? "Student requests" : "Your bookings"));
    if (!bookings.length) root.append(el("p", { class: "muted" }, me.role === "tutor" ? "No requests yet." : "No bookings yet. Find a tutor to get started."));
    for (const b of bookings) {
      const act = (status, label, cls = "") => el("button", { class: cls, onclick: e => run(e.target, async () => { await api("POST", `/bookings/${b.id}/status`, { status }); toast("Updated."); render(); }) }, label);
      const btns = me.role === "tutor" ? (b.status === "Pending" ? [act("Accepted", "Accept"), act("Declined", "Decline", "ghost")] : b.status === "Accepted" ? [act("Completed", "Mark completed")] : [])
                                       : (["Pending", "Accepted"].includes(b.status) ? [act("Cancelled", "Cancel", "danger")] : []);
      root.append(el("div", { class: "card" }, el("div", { class: "row" }, el("b", { class: "grow" }, b.topic), el("span", { class: "pill " + b.status }, b.status)),
        el("div", { class: "muted" }, `${me.role === "tutor" ? "Student" : "Tutor"}: ${b.other_name}${b.slot ? " · " + b.slot : ""}`), b.note ? el("p", {}, b.note) : null, el("div", { class: "row" }, btns)));
    }
  },
  async doubts(root) {
    const list = el("div", {});
    if (me.role === "student") {
      const subject = el("input", { placeholder: "Subject, e.g. Physics" }), question = el("textarea", { rows: 3, placeholder: "What are you stuck on?" });
      const post = el("button", {}, "Post doubt");
      post.onclick = () => run(post, async () => { await api("POST", "/doubts", { subject: subject.value, question: question.value }); toast("Posted."); render(); });
      root.append(el("div", { class: "card" }, field("Subject", subject), field("Your question", question), el("div", { style: "margin-top:12px" }, post)));
    }
    const { doubts } = await api("GET", "/doubts").catch(e => (toast(e.message), { doubts: [] }));
    if (!doubts.length) list.append(el("p", { class: "muted" }, "No doubts posted yet."));
    for (const d of doubts) {
      const input = el("input", { placeholder: "Write a reply" }), send = el("button", { class: "ghost" }, "Reply");
      send.onclick = () => run(send, async () => { await api("POST", `/doubts/${d.id}/replies`, { body: input.value }); render(); });
      list.append(el("div", { class: "card" }, el("b", {}, d.subject), el("span", { class: "muted" }, ` · ${d.student_name}`), el("p", {}, d.question),
        d.replies.map(r => el("div", { class: "reply" }, el("b", {}, r.name), el("span", { class: "muted" }, ` (${r.role}) `), r.body)),
        el("div", { class: "row" }, el("div", { class: "grow" }, input), send)));
    }
    root.append(list);
  },
  profile(root) {
    const f = { name: el("input", { value: me.name }), skills: el("input", { value: me.skills }), city: el("input", { value: me.city }),
      bio: el("textarea", { rows: 3 }, me.bio), rate: el("input", { type: "number", min: 0, value: me.rate }) };
    const save = el("button", {}, "Save profile");
    save.onclick = () => run(save, async () => { me = (await api("PUT", "/me", { name: f.name.value, skills: f.skills.value, city: f.city.value, bio: f.bio.value, rate: f.rate.value })).user; toast("Saved."); render(); });
    root.append(el("div", { class: "card" }, field("Name", f.name), field("Skills", f.skills), field("City", f.city), field("About you", f.bio),
      me.role === "tutor" ? field("Hourly rate (₹)", f.rate) : null, el("p", { class: "muted" }, "Email: " + me.email), save));
  },
};

function tutorCard(t) {
  const topic = el("input", { placeholder: "What do you want to learn?" }), slot = el("input", { placeholder: "Preferred time (optional)" });
  const form = el("div", { hidden: true }, field("Topic", topic), field("Preferred time", slot));
  const send = el("button", {}, "Request session");
  let open = false;
  send.onclick = () => {
    if (!open) { open = true; form.hidden = false; send.textContent = "Send request"; topic.focus(); return; }
    run(send, async () => { await api("POST", "/bookings", { tutor_id: t.id, topic: topic.value, slot: slot.value }); toast("Request sent."); tab = "bookings"; render(); });
  };
  return el("div", { class: "card" }, el("div", { class: "row" }, el("b", { class: "grow" }, t.name), t.rate ? el("span", { class: "pill" }, `₹${t.rate}/hr`) : null),
    el("div", { class: "muted" }, [t.skills, t.city].filter(Boolean).join(" · ") || "No details yet"), t.bio ? el("p", {}, t.bio) : null, form, el("div", { style: "margin-top:12px" }, send));
}

/* ---- backend check: this page is only the front half; it needs the Python server behind it ---- */
async function backendUp() {
  try { const r = await fetch("api/health"); return r.ok && (await r.json()).status === "ok"; } catch { return false; }
}
function noBackendView() {
  const code = t => el("pre", { class: "card", style: "overflow:auto" }, t);
  return el("div", { class: "auth", style: "max-width:640px" }, el("h1", {}, "🎓 EduBridge AI"),
    el("div", { class: "card" }, el("h2", { style: "margin-top:0" }, "The backend server isn't running"),
      el("p", {}, "You are seeing the website files only. EduBridge needs its Python server, which also serves this page. Opening index.html directly, or hosting on GitHub Pages, can't work."),
      el("b", {}, "Run it on your computer:"), code("pip install -r requirements.txt\npython app.py\n# then open http://localhost:8000"),
      el("b", {}, "Or put it online:"), el("p", {}, "Deploy the repository on Render (see README) and open the URL Render gives you."),
      el("button", { onclick: () => location.reload() }, "Try again")));
}

async function render() {
  if (!(await backendUp())) return $app.replaceChildren(noBackendView());
  if (!token) return $app.replaceChildren(authView());
  if (!me) { try { me = (await api("GET", "/me")).user; } catch { return; } }
  $app.replaceChildren(shell());
}
render();
