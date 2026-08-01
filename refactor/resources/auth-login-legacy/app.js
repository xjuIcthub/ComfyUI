const config = window.ICTHUB_AUTH_CONFIG ?? {};
const workspaceLink = document.querySelector("#workspace-link");
const registrationLink = document.querySelector("#registration-link");
const registrationForm = document.querySelector("#registration-form");
const registrationInput = document.querySelector("#invitation-token");
const registrationSubmit = document.querySelector("#registration-submit");
const currentYear = document.querySelector("#current-year");

if (currentYear) {
  currentYear.textContent = new Date().getFullYear();
}

if (workspaceLink) {
  const returnTo = new URLSearchParams(window.location.search).get("returnTo");
  if (returnTo) {
    const destination = new URL(returnTo, "https://comfy.icthub.top");
    if (destination.origin === "https://comfy.icthub.top") {
      workspaceLink.href = destination.toString();
    }
  }

  workspaceLink.addEventListener("click", () => {
    workspaceLink.classList.add("is-leaving");
    workspaceLink.querySelector("span").textContent = "正在进入工作台…";
  });
}

if (registrationLink) {
  if (config.registrationEnabled === true) {
    registrationLink.removeAttribute("aria-disabled");
    registrationLink.querySelector("span").textContent = "邀请码注册";
  } else {
    registrationLink.addEventListener("click", (event) => event.preventDefault());
  }
}

if (registrationForm && registrationInput && registrationSubmit) {
  if (config.registrationEnabled === true) {
    registrationInput.disabled = false;
    registrationSubmit.disabled = false;
    registrationSubmit.querySelector("span").textContent = "验证邀请码并注册";
  }

  registrationForm.addEventListener("submit", () => {
    registrationSubmit.disabled = true;
    registrationSubmit.classList.add("is-leaving");
    registrationSubmit.querySelector("span").textContent = "正在前往安全注册页…";
  });
}
