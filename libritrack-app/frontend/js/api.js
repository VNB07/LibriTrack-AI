// Talks to the FastAPI backend. Every request except login sends the staff token.
const API = "/api";

const Session = {
  get token() { return sessionStorage.getItem("token"); },
  set token(value) { value ? sessionStorage.setItem("token", value) : sessionStorage.removeItem("token"); },
  get name() { return sessionStorage.getItem("name"); },
  set name(value) { value ? sessionStorage.setItem("name", value) : sessionStorage.removeItem("name"); }
};

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (Session.token) headers.Authorization = "Bearer " + Session.token;
  let payload;
  if (form) {
    payload = form;                       // FormData: browser sets the multipart header
  } else if (body) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(API + path, { method, headers, body: payload });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "/auth/login") {
    Session.token = null;                 // expired session: back to login
    location.reload();
  }
  if (!res.ok) {
    let msg = "Request failed";
    if (typeof data.detail === "string") {
      msg = data.detail;
    } else if (Array.isArray(data.detail) && data.detail.length > 0) {
      msg = data.detail.map(d => (d.loc ? d.loc.slice(-1)[0] + ": " : "") + d.msg).join(", ");
    }
    throw new Error(msg);
  }
  return data;
}