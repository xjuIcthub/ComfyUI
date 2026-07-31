const workspaceLink = document.querySelector("#workspace-link");
const currentYear = document.querySelector("#current-year");

currentYear.textContent = new Date().getFullYear();

const returnTo = new URLSearchParams(window.location.search).get("returnTo");
if (returnTo?.startsWith("/") && !returnTo.startsWith("//")) {
  workspaceLink.href = new URL(returnTo, "https://comfy.icthub.top").toString();
}

workspaceLink.addEventListener("click", () => {
  workspaceLink.classList.add("is-leaving");
  workspaceLink.querySelector("span").textContent = "正在进入工作台…";
});
