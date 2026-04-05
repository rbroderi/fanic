/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 * FANIC_ASSET_VERSION: 20260404
 */

type DonationPayload = {
  ok?: boolean;
  label?: string;
  current_total?: number;
  goal_total?: number;
  progress_ratio?: number;
  currency?: string;
};

function formatCurrency(amount: number, currencyCode: string): string {
  const safeAmount = Number.isFinite(amount) ? amount : 0;
  const code = currencyCode.trim() ? currencyCode : "USD";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: code,
    maximumFractionDigits: 0,
  }).format(safeAmount);
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  if (value < 0) {
    return 0;
  }
  if (value > 100) {
    return 100;
  }
  return value;
}

(function () {
  const shell = document.querySelector<HTMLElement>("[data-donation-progress]");
  if (!shell) {
    return;
  }

  const labelNode = document.getElementById("donationProgressLabel");
  const fillNode = document.getElementById("donationProgressFill");
  const totalNode = document.getElementById("donationProgressTotal");

  if (!fillNode || !totalNode) {
    return;
  }

  fetch("/api/donations-progress", {
    method: "GET",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
    },
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`donations-progress status ${response.status}`);
      }
      return response.json() as Promise<DonationPayload>;
    })
    .then((payload) => {
      const goalTotal = Number(payload.goal_total);
      const currentTotal = Number(payload.current_total);
      const ratio = Number(payload.progress_ratio);
      const currency = typeof payload.currency === "string" ? payload.currency : "USD";

      const percent = clampPercent(ratio * 100);
      fillNode.style.width = `${percent}%`;

      const goalSafe = Number.isFinite(goalTotal) && goalTotal > 0 ? goalTotal : 1;
      const currentSafe = Number.isFinite(currentTotal) ? currentTotal : 0;

      totalNode.textContent = `${formatCurrency(currentSafe, currency)} / ${formatCurrency(goalSafe, currency)}`;
      if (labelNode && typeof payload.label === "string" && payload.label.trim()) {
        labelNode.textContent = payload.label;
      }

      shell.hidden = false;
    })
    .catch(() => {
      shell.hidden = true;
    });
})();
