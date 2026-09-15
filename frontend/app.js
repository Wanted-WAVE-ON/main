const API = "/api/v1";
const USER_ID = "demo-user";

const contextDefinitions = {
  presentation: {
    title: "Presentation",
    app: "PowerPoint",
    appIcon: "P",
    meta: "Meeting room / Laptop",
    space: "meeting_room",
    actions: [
      { intent: "NEXT_SLIDE", target: "powerpoint" },
      { intent: "PREVIOUS_SLIDE", target: "powerpoint" },
      { intent: "START_PRESENTATION", target: "powerpoint" },
    ],
  },
  music: {
    title: "Music",
    app: "Spotify",
    appIcon: "S",
    meta: "Desk / Laptop",
    space: "desk",
    actions: [
      { intent: "NEXT_TRACK", target: "media_player" },
      { intent: "PREVIOUS_TRACK", target: "media_player" },
      { intent: "TOGGLE_PLAYBACK", target: "media_player" },
    ],
  },
};

const gestureSymbols = {
  "swipe:right": "→",
  "swipe:left": "←",
  "open_palm:none": "▢",
  "circle:clockwise": "○",
};

// Reserved hands-free confirm gestures (backend: services/confirmation.py) -
// they answer a pending suggestion or recent execution instead of being
// taught as a new gesture, so they skip the usual "what did you do next" step.
const CONFIRM_GESTURES = new Set(["open_palm:none", "circle:clockwise"]);

let currentContext = "presentation";
let lastObservation = null;
let lastGestureLabel = null;
let lastGestureSymbol = null;
let lastExecution = null;
let dashboardState = null;
let dashboardRequest = null;
let suggestionSignature = null;
let lastGestureButton = null;
let cameraStream = null;
let cameraCanvas = null;
let cameraContext = null;
let cameraPreviousFrame = null;
let cameraAnimationFrame = null;
let cameraLastSampleAt = 0;
let cameraMotionStartAt = null;
let cameraMotionDistance = 0;
let cameraDirectionHistory = [];
let cameraLastDetectionAt = 0;
let cameraSubmitting = false;
let cameraDeviceId = "";
let cameraBackgroundFrame = null;
let cameraPalmStableCount = 0;
let cameraPalmActive = false;
let cameraCircleSamples = [];
// Filled from /demo/bootstrap so the labels have one source of truth.
let intentLabels = {};
let autoExecutionThreshold = 0.6;
let osActionsEnabled = false;
let demoModeEnabled = true;

const CAMERA_SAMPLE_WIDTH = 160;
const CAMERA_SAMPLE_HEIGHT = 90;
const CAMERA_SAMPLE_INTERVAL_MS = 90;
const CAMERA_STABLE_SAMPLES = 3;
const CAMERA_COOLDOWN_MS = 1200;
// A slow exponential-average "background" plate lets us tell a large object
// that just entered frame (a raised palm) apart from ordinary frame noise -
// the same idea as the Python client's cv2 MOG2 subtractor, done per-pixel.
const CAMERA_BACKGROUND_ALPHA = 0.05;
const CAMERA_MOTION_THRESHOLD = 20;
const CAMERA_BACKGROUND_THRESHOLD = 26;
const CAMERA_PALM_COVERAGE_RATIO = 0.35;
const CAMERA_PALM_STILL_RATIO = 0.05;
const CAMERA_PALM_RESET_RATIO = 0.15;
const CAMERA_PALM_STABLE_SAMPLES = 5;
const CAMERA_CIRCLE_MIN_RATIO = 0.015;
const CAMERA_CIRCLE_MAX_RATIO = 0.4;
const CAMERA_CIRCLE_WINDOW_MS = 2600;
const CAMERA_CIRCLE_GAP_MS = 350;
const CAMERA_CIRCLE_MIN_RADIUS = 6;
const CAMERA_CIRCLE_MIN_ROTATION = Math.PI * 1.6;
const CAMERA_GESTURE_LABELS = {
  "swipe:right": "오른쪽 손짓",
  "swipe:left": "왼쪽 손짓",
  "open_palm:none": "손바닥 펼치기",
  "circle:clockwise": "원형 움직임",
};

const byId = (id) => document.getElementById(id);
const all = (selector, root = document) => root.querySelectorAll(selector);
const intentLabel = (intent) => intentLabels[intent] || intent;

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      detail = (await response.json()).detail || detail;
    } catch (_) {
      // Keep the HTTP status when the response body is not JSON.
    }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

const post = (path, body = {}) => request(path, {
  method: "POST",
  body: JSON.stringify(body),
});

// Disable the given controls while `task` runs. A control the task marked with
// its own data-state (e.g. "error") keeps it.
async function withBusy(controls, task) {
  const buttons = [...controls];
  buttons.forEach((button) => {
    button.disabled = true;
    button.dataset.state = "loading";
    button.setAttribute("aria-busy", "true");
  });
  try {
    return await task();
  } finally {
    buttons.forEach((button) => {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      if (button.dataset.state === "loading") button.removeAttribute("data-state");
    });
  }
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2400);
}

function setAgentState(kind, title, description) {
  const orb = byId("agentOrb");
  orb.classList.remove("listening", "success");
  if (kind) orb.classList.add(kind);
  byId("agentStatus").textContent = kind === "listening"
    ? "제스처 관찰 중"
    : kind === "success" ? "의도 실행 완료" : "공간을 이해하는 중";
  byId("stageTitle").textContent = title;
  byId("stageDescription").textContent = description;
}

function renderContext() {
  const definition = contextDefinitions[currentContext];
  byId("contextTitle").textContent = definition.title;
  byId("activeApp").textContent = definition.app;
  byId("appIcon").textContent = definition.appIcon;
  byId("contextMeta").textContent = definition.meta;
  all(".segment").forEach((button) => {
    const isActive = button.dataset.context === currentContext;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  renderActionButtons();
  renderInterpretations(dashboardState?.memories || []);
}

function renderActionButtons() {
  const host = byId("actionButtons");
  if (!lastObservation) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = contextDefinitions[currentContext].actions
    .map((action) => `<button class="action-button" type="button" data-intent="${action.intent}" data-target="${action.target}">${intentLabel(action.intent)}</button>`)
    .join("");
  all(".action-button", host).forEach((button) => {
    button.addEventListener("click", () => teachAction(button.dataset.intent, button.dataset.target));
  });
}

async function processObservation(result, motion, direction, label, symbol) {
  lastGestureLabel = label;
  lastGestureSymbol = symbol;
  lastObservation = result.observation;

  if (CONFIRM_GESTURES.has(`${motion}:${direction}`)) {
    setAgentState(
      result.inference.matched ? "success" : "",
      result.inference.matched ? "확인했어요" : "확인 몸짓",
      result.inference.reason,
    );
    showToast(result.inference.reason);
    lastObservation = null;
    renderActionButtons();
    await refreshDashboard();
    return;
  }

  if (result.inference.matched) {
    lastExecution = result.inference.execution;
    const failed = result.inference.execution?.status === "FAILED";
    setAgentState(
      failed ? "" : "success",
      failed ? `${intentLabel(result.inference.intent)} 실행 실패` : intentLabel(result.inference.intent),
      failed ? executionError(result.inference.execution) : result.inference.reason,
    );
    showActionOverlay(result.inference);
    lastObservation = null;
    updateTeachingCard(
      failed ? "자동 실행 실패" : "자동 실행 완료",
      failed
        ? "의도는 추론했지만 동작을 전달하지 못했습니다. 아래 사유를 확인해 주세요."
        : "Agent가 현재 맥락과 개인 기억을 바탕으로 의도를 추론했습니다.",
    );
  } else {
    setAgentState(
      "",
      "다음 행동을 알려주세요",
      "몸짓 직후 실제로 하려던 행동을 선택하면 반복 패턴을 학습합니다.",
    );
    updateTeachingCard(`${lastGestureLabel} 관찰 완료`, "이 몸짓 직후 사용자가 한 행동을 선택해 주세요.");
    renderActionButtons();
  }
  await refreshDashboard();
}

function observationPayload(motion, direction, durationMs, speed, amplitude) {
  const context = contextDefinitions[currentContext];
  return {
    user_id: USER_ID,
    context: {
      active_app: context.app,
      activity: currentContext,
      space: context.space,
      device: "laptop",
    },
    gesture: {
      motion_type: motion,
      direction,
      duration_ms: durationMs,
      ...(speed === undefined ? {} : { speed, amplitude }),
    },
    attempt_inference: true,
  };
}

async function observeGesture(button) {
  const motion = button.dataset.motion;
  const direction = button.dataset.direction;
  lastGestureButton = button;
  all(".gesture-button").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  setAgentState("listening", "동작을 관찰하고 있어요", "모션 특징과 현재 상황만 분석합니다. 원본 프레임은 저장하지 않습니다.");

  await withBusy([button], async () => {
    try {
      const result = await post("/observe", observationPayload(motion, direction, 430));
      await processObservation(result, motion, direction, button.dataset.label, gestureSymbols[`${motion}:${direction}`] || "?");
    } catch (error) {
      showToast(`관찰 실패: ${error.message}`);
      button.dataset.state = "error";
      setAgentState("", "다시 시도해 주세요", "API 연결 상태와 서버 로그를 확인해 주세요.");
    }
  });
}

function luminance(frame, offset) {
  return (frame[offset] * 0.2126) + (frame[offset + 1] * 0.7152) + (frame[offset + 2] * 0.0722);
}

function detectHorizontalMotion(previous, current, width, height) {
  if (!previous || !current || previous.length !== current.length) return null;
  const searchRadius = 6;
  const sampleStep = 2;
  let samples = 0;
  let movingSamples = 0;
  let horizontalGain = 0;
  let verticalGain = 0;
  let weightedDisplacement = 0;

  for (let y = searchRadius; y < height - searchRadius; y += sampleStep) {
    for (let x = searchRadius; x < width - searchRadius; x += sampleStep) {
      const offset = ((y * width) + x) * 4;
      const currentValue = luminance(current, offset);
      const stationaryError = Math.abs(currentValue - luminance(previous, offset));
      samples += 1;
      if (stationaryError < 24) continue;

      let bestHorizontalError = stationaryError;
      let bestHorizontalShift = 0;
      let bestVerticalError = stationaryError;
      for (let shift = -searchRadius; shift <= searchRadius; shift += 1) {
        const horizontalOffset = ((y * width) + (x - shift)) * 4;
        const verticalOffset = (((y - shift) * width) + x) * 4;
        const horizontalError = Math.abs(currentValue - luminance(previous, horizontalOffset));
        const verticalError = Math.abs(currentValue - luminance(previous, verticalOffset));
        if (horizontalError < bestHorizontalError) {
          bestHorizontalError = horizontalError;
          bestHorizontalShift = shift;
        }
        if (verticalError < bestVerticalError) bestVerticalError = verticalError;
      }

      const horizontalImprovement = stationaryError - bestHorizontalError;
      const verticalImprovement = stationaryError - bestVerticalError;
      if (Math.abs(bestHorizontalShift) < 1 || horizontalImprovement < 12) continue;
      movingSamples += 1;
      horizontalGain += horizontalImprovement;
      verticalGain += Math.max(0, verticalImprovement);
      weightedDisplacement += bestHorizontalShift * horizontalImprovement;
    }
  }

  if (!samples || !horizontalGain || movingSamples / samples < 0.004 || horizontalGain <= verticalGain * 1.1) return null;
  const displacement = weightedDisplacement / horizontalGain;
  if (Math.abs(displacement) < 1) return null;
  return { direction: displacement > 0 ? "right" : "left", displacement, ratio: movingSamples / samples };
}

function clampFeature(value) {
  return Math.min(10, Number(value.toFixed(3)));
}

// Coarser than detectHorizontalMotion: just "how much changed, and where" -
// enough to notice a large still object (open palm) or a moving blob's path
// (circle) without the swipe detector's directional block matching.
function analyzeMotionField(previous, current, width, height, threshold) {
  if (!previous || !current || previous.length !== current.length) return null;
  let count = 0;
  let sumX = 0;
  let sumY = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = ((y * width) + x) * 4;
      const diff = Math.abs(luminance(current, offset) - luminance(previous, offset));
      if (diff < threshold) continue;
      count += 1;
      sumX += x;
      sumY += y;
    }
  }
  const total = width * height;
  if (!count) return { ratio: 0, centroidX: null, centroidY: null };
  return { ratio: count / total, centroidX: sumX / count, centroidY: sumY / count };
}

function updateCameraBackground(frame) {
  if (!cameraBackgroundFrame) {
    cameraBackgroundFrame = Float32Array.from(frame);
    return;
  }
  for (let i = 0; i < frame.length; i += 1) {
    cameraBackgroundFrame[i] += (frame[i] - cameraBackgroundFrame[i]) * CAMERA_BACKGROUND_ALPHA;
  }
}

// A palm filling the frame shows up as (a) a big departure from the learned
// background and (b) very little further change once it is held still.
function trackOpenPalm(background, field, timestamp) {
  if (!background) return null;
  const filling = background.ratio >= CAMERA_PALM_COVERAGE_RATIO;
  const still = !field || field.ratio <= CAMERA_PALM_STILL_RATIO;
  cameraPalmStableCount = filling && still ? cameraPalmStableCount + 1 : 0;
  if (background.ratio < CAMERA_PALM_RESET_RATIO) cameraPalmActive = false;
  if (cameraPalmActive || cameraPalmStableCount < CAMERA_PALM_STABLE_SAMPLES) return null;
  cameraPalmActive = true;
  return { coverage: background.ratio };
}

// Sums the signed angle a moving blob's centroid sweeps around its own
// trajectory's centre; a full loop (either sense) means "circle".
function computeCircleRotation(samples) {
  if (samples.length < 4) return { rotation: 0, radius: 0 };
  let cx = 0;
  let cy = 0;
  samples.forEach((sample) => {
    cx += sample.x;
    cy += sample.y;
  });
  cx /= samples.length;
  cy /= samples.length;
  let rotation = 0;
  let radiusSum = 0;
  let previousAngle = null;
  samples.forEach((sample) => {
    const dx = sample.x - cx;
    const dy = sample.y - cy;
    radiusSum += Math.hypot(dx, dy);
    const angle = Math.atan2(dy, dx);
    if (previousAngle !== null) {
      let delta = angle - previousAngle;
      if (delta > Math.PI) delta -= Math.PI * 2;
      if (delta < -Math.PI) delta += Math.PI * 2;
      rotation += delta;
    }
    previousAngle = angle;
  });
  return { rotation, radius: radiusSum / samples.length };
}

function trackCircleMotion(field, timestamp) {
  const inBand = field && field.ratio >= CAMERA_CIRCLE_MIN_RATIO && field.ratio <= CAMERA_CIRCLE_MAX_RATIO;
  if (!inBand) {
    if (cameraCircleSamples.length && timestamp - cameraCircleSamples.at(-1).t > CAMERA_CIRCLE_GAP_MS) cameraCircleSamples = [];
    return null;
  }
  cameraCircleSamples.push({ x: field.centroidX, y: field.centroidY, t: timestamp });
  const cutoff = timestamp - CAMERA_CIRCLE_WINDOW_MS;
  cameraCircleSamples = cameraCircleSamples.filter((sample) => sample.t >= cutoff);
  const { rotation, radius } = computeCircleRotation(cameraCircleSamples);
  if (radius < CAMERA_CIRCLE_MIN_RADIUS || Math.abs(rotation) < CAMERA_CIRCLE_MIN_ROTATION) return null;
  return { durationMs: timestamp - cameraCircleSamples[0].t, radius, rotation };
}

function setCameraStatus(message, state = "idle") {
  byId("cameraStatus").textContent = message;
  byId("cameraPreview").dataset.state = state;
  byId("cameraMode").textContent = state === "active" ? "Local camera" : state === "error" ? "Camera error" : "Camera off";
  byId("cameraLive").hidden = state !== "active";
}

async function populateCameraDevices(activeDeviceId) {
  const select = byId("cameraDeviceSelect");
  const devices = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
  select.innerHTML = devices.map((device, index) => (
    `<option value="${device.deviceId}">${device.label || `카메라 ${index + 1}`}</option>`
  )).join("");
  select.disabled = !devices.length;
  const matchingDevice = devices.some((device) => device.deviceId === activeDeviceId);
  if (matchingDevice) select.value = activeDeviceId;
  cameraDeviceId = select.value || "";
}

function resetCameraMotion() {
  cameraPreviousFrame = null;
  cameraMotionStartAt = null;
  cameraMotionDistance = 0;
  cameraDirectionHistory = [];
  cameraPalmStableCount = 0;
  cameraCircleSamples = [];
}

async function submitCameraGesture(motion, direction, durationMs, speed, amplitude) {
  if (cameraSubmitting) return;
  cameraSubmitting = true;
  try {
    const result = await post("/observe", observationPayload(motion, direction, durationMs, speed, amplitude));
    const label = CAMERA_GESTURE_LABELS[`${motion}:${direction}`] || `${motion} 손짓`;
    await processObservation(result, motion, direction, label, gestureSymbols[`${motion}:${direction}`] || "?");
  } catch (error) {
    showToast(`카메라 관찰 실패: ${error.message}`);
    setAgentState("", "다시 시도해 주세요", "서버 연결 상태를 확인해 주세요.");
  } finally {
    cameraSubmitting = false;
  }
}

function processCameraFrame(timestamp) {
  if (!cameraStream) return;
  cameraAnimationFrame = window.requestAnimationFrame(processCameraFrame);
  const video = byId("cameraVideo");
  if (video.readyState < 2 || timestamp - cameraLastSampleAt < CAMERA_SAMPLE_INTERVAL_MS) return;
  cameraLastSampleAt = timestamp;
  cameraContext.save();
  cameraContext.translate(CAMERA_SAMPLE_WIDTH, 0);
  cameraContext.scale(-1, 1);
  cameraContext.drawImage(video, 0, 0, CAMERA_SAMPLE_WIDTH, CAMERA_SAMPLE_HEIGHT);
  cameraContext.restore();
  const frame = cameraContext.getImageData(0, 0, CAMERA_SAMPLE_WIDTH, CAMERA_SAMPLE_HEIGHT).data;

  const motion = detectHorizontalMotion(cameraPreviousFrame, frame, CAMERA_SAMPLE_WIDTH, CAMERA_SAMPLE_HEIGHT);
  const field = analyzeMotionField(cameraPreviousFrame, frame, CAMERA_SAMPLE_WIDTH, CAMERA_SAMPLE_HEIGHT, CAMERA_MOTION_THRESHOLD);
  const background = analyzeMotionField(cameraBackgroundFrame, frame, CAMERA_SAMPLE_WIDTH, CAMERA_SAMPLE_HEIGHT, CAMERA_BACKGROUND_THRESHOLD);
  updateCameraBackground(frame);
  cameraPreviousFrame = new Uint8ClampedArray(frame);

  const ready = timestamp - cameraLastDetectionAt >= CAMERA_COOLDOWN_MS;
  const palm = ready ? trackOpenPalm(background, field, timestamp) : null;
  const circle = ready && !palm ? trackCircleMotion(field, timestamp) : null;

  if (!motion) {
    cameraDirectionHistory = [];
    cameraMotionStartAt = null;
    cameraMotionDistance = 0;
  } else {
    if (cameraDirectionHistory.at(-1) !== motion.direction) {
      cameraDirectionHistory = [];
      cameraMotionStartAt = timestamp;
      cameraMotionDistance = 0;
    }
    cameraDirectionHistory.push(motion.direction);
    cameraDirectionHistory = cameraDirectionHistory.slice(-CAMERA_STABLE_SAMPLES);
    cameraMotionDistance += Math.abs(motion.displacement);
    setCameraStatus(`${motion.direction === "right" ? "오른쪽" : "왼쪽"} 손짓을 분석 중입니다.`, "active");
  }

  if (palm) {
    cameraLastDetectionAt = timestamp;
    setCameraStatus("손바닥 펼치기를 인식했습니다. 다음 행동을 선택해 주세요.", "active");
    resetCameraMotion();
    submitCameraGesture("open_palm", "none", CAMERA_PALM_STABLE_SAMPLES * CAMERA_SAMPLE_INTERVAL_MS);
    return;
  }

  if (circle) {
    // Radius and angular speed are genuine per-person shape signals (how big
    // and how fast someone draws the loop), unlike open_palm's plain hold -
    // so, like swipe, encode them instead of sending bare motion_type/direction.
    const circleDurationMs = Math.max(1, Math.round(circle.durationMs));
    const circleAmplitude = clampFeature(circle.radius / CAMERA_SAMPLE_WIDTH);
    const circleSpeed = clampFeature(Math.abs(circle.rotation) / (circleDurationMs / 1000));
    cameraLastDetectionAt = timestamp;
    setCameraStatus("원형 움직임을 인식했습니다. 다음 행동을 선택해 주세요.", "active");
    resetCameraMotion();
    submitCameraGesture("circle", "clockwise", circleDurationMs, circleSpeed, circleAmplitude);
    return;
  }

  if (!ready || cameraDirectionHistory.length < CAMERA_STABLE_SAMPLES) return;
  const durationMs = Math.max(1, Math.round(timestamp - cameraMotionStartAt));
  const speed = clampFeature(cameraMotionDistance / CAMERA_SAMPLE_WIDTH / (durationMs / 1000));
  const amplitude = clampFeature(cameraMotionDistance / CAMERA_SAMPLE_WIDTH);
  const direction = cameraDirectionHistory[0];
  cameraLastDetectionAt = timestamp;
  setCameraStatus(`${direction === "right" ? "오른쪽" : "왼쪽"} 손짓을 관찰했습니다. 다음 행동을 선택해 주세요.`, "active");
  resetCameraMotion();
  submitCameraGesture("swipe", direction, durationMs, speed, amplitude);
}

async function startCamera(restart = false) {
  if (cameraStream && !restart) return;
  const startButton = byId("startCameraButton");
  const stopButton = byId("stopCameraButton");
  try {
    if (cameraStream) stopCamera(false);
    startButton.disabled = true;
    setCameraStatus("카메라 권한을 요청하는 중입니다.");
    cameraStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        ...(cameraDeviceId ? { deviceId: { exact: cameraDeviceId } } : { facingMode: "user" }),
        width: { ideal: 640 },
        height: { ideal: 480 },
      },
    });
    const video = byId("cameraVideo");
    video.srcObject = cameraStream;
    await video.play();
    const activeDeviceId = cameraStream.getVideoTracks()[0]?.getSettings().deviceId;
    await populateCameraDevices(activeDeviceId);
    cameraCanvas = document.createElement("canvas");
    cameraCanvas.width = CAMERA_SAMPLE_WIDTH;
    cameraCanvas.height = CAMERA_SAMPLE_HEIGHT;
    cameraContext = cameraCanvas.getContext("2d", { willReadFrequently: true });
    resetCameraMotion();
    cameraBackgroundFrame = null;
    cameraPalmActive = false;
    cameraLastSampleAt = 0;
    cameraLastDetectionAt = 0;
    setCameraStatus("카메라가 이 브라우저에서만 동작 중입니다. 좌우 손짓, 손바닥 펼치기, 원형 움직임을 인식합니다.", "active");
    stopButton.disabled = false;
    cameraAnimationFrame = window.requestAnimationFrame(processCameraFrame);
  } catch (error) {
    stopCamera();
    setCameraStatus(`카메라를 시작하지 못했습니다: ${error.message || "권한 또는 장치를 확인해 주세요."}`, "error");
  } finally {
    startButton.disabled = Boolean(cameraStream);
  }
}

function stopCamera(updateStatus = true) {
  if (cameraAnimationFrame !== null) window.cancelAnimationFrame(cameraAnimationFrame);
  cameraAnimationFrame = null;
  cameraStream?.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  cameraCanvas = null;
  cameraContext = null;
  byId("cameraVideo").srcObject = null;
  byId("startCameraButton").disabled = false;
  byId("stopCameraButton").disabled = true;
  resetCameraMotion();
  cameraBackgroundFrame = null;
  cameraPalmActive = false;
  if (updateStatus) setCameraStatus("카메라가 중지됐습니다. 원본 영상은 저장하거나 전송하지 않았습니다.");
}

async function changeCameraDevice() {
  cameraDeviceId = byId("cameraDeviceSelect").value;
  await startCamera(true);
}

function updateTeachingCard(title, description) {
  byId("teachingTitle").textContent = title;
  byId("teachingDescription").textContent = description;
}

async function teachAction(intent, target) {
  if (!lastObservation) return;
  await withBusy(all(".action-button"), async () => {
    try {
      const result = await post("/teach", {
        user_id: USER_ID,
        observation_id: lastObservation.id,
        action_type: intent,
        target,
        parameters: {},
      });
      const label = intentLabel(intent);
      updateTeachingCard(
        `학습 진행 ${result.progress_current}/${result.progress_required}`,
        `${lastGestureLabel} → ${label} 연결성을 관찰했습니다.`,
      );
      setAgentState(
        "",
        `패턴을 학습하고 있어요 / ${result.progress_current}/${result.progress_required}`,
        "같은 상황에서 행동이 반복되면 먼저 제안하고, 승인 후에만 자동 실행합니다.",
      );
      if (result.suggestion?.status === "PENDING") {
        showToast("새로운 패턴을 발견했습니다. 기억 여부를 확인해 주세요.");
      }
      lastObservation = null;
      renderActionButtons();
      await refreshDashboard();
    } catch (error) {
      showToast(`학습 실패: ${error.message}`);
    }
  });
}

async function respondSuggestion(id, decision, modifiedIntent = null) {
  await withBusy(all("[data-decision]"), async () => {
    try {
      await post(`/suggestions/${id}/respond`, {
        decision,
        ...(modifiedIntent ? { modified_intent: modifiedIntent } : {}),
      });
      if (decision === "ACCEPTED" || decision === "MODIFIED") {
        setAgentState(
          "success",
          "새로운 몸짓 언어를 기억했어요",
          "이제 같은 상황에서 이 몸짓을 사용하면 Agent가 자동으로 실행합니다.",
        );
      }
      await refreshDashboard();
    } catch (error) {
      showToast(`제안 처리 실패: ${error.message}`);
    }
  });
}

const executionError = (execution) => execution?.error_message
  || "동작을 전달하지 못했습니다. 대상 앱과 실행 권한을 확인해 주세요.";

function showActionOverlay(inference) {
  const overlay = byId("actionOverlay");
  const failed = inference.execution?.status === "FAILED";
  overlay.dataset.status = failed ? "failed" : "success";
  byId("overlayGesture").textContent = failed ? "!" : (lastGestureSymbol || "?");
  byId("overlayAction").textContent = failed
    ? `${intentLabel(inference.intent)} 실행 실패`
    : intentLabel(inference.intent);
  byId("overlayConfidence").textContent =
    `${currentContext} / ${Math.round(inference.confidence * 100)}%`
    + (failed ? ` / ${executionError(inference.execution)}` : "");
  // ponytail: no auto-close timer - the feedback buttons live in here, and a
  // presenter narrating the execution needs longer than any timeout we'd pick.
  // Esc and a backdrop click already dismiss it.
  if (!overlay.open) overlay.showModal();
}

function closeActionOverlay() {
  const overlay = byId("actionOverlay");
  if (overlay.open) overlay.close();
}

const TUTORIAL_HIDE_KEY = "so_tutorial_hidden_until";
const TUTORIAL_SLIDE_COUNT = all(".tutorial-slide").length;
let tutorialSlideIndex = 0;

function todayKey() {
  return new Date().toLocaleDateString("en-CA");
}

function isTutorialHiddenToday() {
  try {
    return window.localStorage.getItem(TUTORIAL_HIDE_KEY) === todayKey();
  } catch (_) {
    return false;
  }
}

function renderTutorialSlide() {
  all(".tutorial-slide").forEach((slide, index) => {
    slide.hidden = index !== tutorialSlideIndex;
  });
  const dots = byId("tutorialDots");
  dots.innerHTML = Array.from({ length: TUTORIAL_SLIDE_COUNT }, (_, index) => (
    `<button class="tutorial-dot${index === tutorialSlideIndex ? " active" : ""}" type="button" data-slide-index="${index}" aria-label="${index + 1}단계로 이동"></button>`
  )).join("");
  all("[data-slide-index]", dots).forEach((dot) => {
    dot.addEventListener("click", () => {
      tutorialSlideIndex = Number(dot.dataset.slideIndex);
      renderTutorialSlide();
    });
  });
  const isLast = tutorialSlideIndex === TUTORIAL_SLIDE_COUNT - 1;
  byId("tutorialPrev").hidden = tutorialSlideIndex === 0;
  byId("tutorialNext").textContent = isLast ? "시작하기" : "다음";
}

function openTutorial() {
  tutorialSlideIndex = 0;
  byId("tutorialHideToday").checked = false;
  renderTutorialSlide();
  const overlay = byId("tutorialOverlay");
  if (!overlay.open) overlay.showModal();
}

function closeTutorial() {
  const overlay = byId("tutorialOverlay");
  if (overlay.open) overlay.close();
}

async function submitFeedback(type) {
  if (!lastExecution) return;
  await withBusy(all("[data-feedback]"), async () => {
    try {
      await post(`/executions/${lastExecution.id}/feedback`, {
        user_id: USER_ID,
        feedback_type: type,
      });
      closeActionOverlay();
      lastExecution = null;
      await refreshDashboard();
    } catch (error) {
      showToast(`피드백 실패: ${error.message}`);
    }
  });
}

function renderSuggestions(suggestions, candidates) {
  const host = byId("suggestionContent");
  const signature = JSON.stringify([suggestions, candidates, intentLabels]);
  if (signature === suggestionSignature) return;
  suggestionSignature = signature;
  if (!suggestions.length) {
    host.dataset.state = "empty";
    host.innerHTML = `<div class="empty-state"><span aria-hidden="true">—</span><p>같은 몸짓과 후속 행동이 3회 반복되면 Agent가 기억을 제안합니다.</p></div>`;
    return;
  }
  host.dataset.state = "pending";
  const suggestion = suggestions[0];
  const confidence = Math.round(suggestion.confidence * 100);
  const pattern = candidates.find((item) => item.id === suggestion.gesture_pattern_id);
  const intents = contextDefinitions[pattern?.context_scope]?.actions.map((action) => action.intent)
    || [suggestion.suggested_intent];
  const intentOptions = intents.map((intent) => (
    `<option value="${intent}" ${intent === suggestion.suggested_intent ? "selected" : ""}>${intentLabel(intent)}</option>`
  )).join("");
  host.innerHTML = `
    <div class="suggestion-card">
      <h3>이 몸짓을 “${intentLabel(suggestion.suggested_intent)}”로 기억할까요?</h3>
      <p>${suggestion.reason}</p>
      <div class="confidence-bar"><i style="width:${confidence}%"></i></div>
      <label class="suggestion-intent-label" for="modifiedIntent">수정할 의도</label>
      <select class="suggestion-intent-input" id="modifiedIntent">${intentOptions}</select>
      <div class="suggestion-actions">
        <button class="primary-button" type="button" data-decision="ACCEPTED">기억하기</button>
        <button class="secondary-button" type="button" data-decision="MODIFIED">수정</button>
        <button class="secondary-button" type="button" data-decision="REJECTED">아니요</button>
      </div>
    </div>`;
  all("[data-decision]", host).forEach((button) => {
    button.addEventListener("click", () => {
      const decision = button.dataset.decision;
      if (decision !== "MODIFIED") return respondSuggestion(suggestion.id, decision);
      const modifiedIntent = host.querySelector("#modifiedIntent").value;
      return respondSuggestion(suggestion.id, decision, modifiedIntent);
    });
  });
}

// FR-13 (auto demotion) has no dedicated event log on the backend - a
// CANDIDATE with observation_count already past the suggestion threshold can
// only have gotten there by being ACTIVE first, so we infer "demoted" rather
// than "still forming" from that alone. Best-effort, frontend-only signal.
function inferDemotionReason(candidate) {
  return candidate.negative_feedback_count > 0
    ? "부정 피드백 누적으로 신뢰도가 낮아져 대기 상태로 전환된 것으로 추정"
    : "다른 후속 행동과 판단이 엇갈려 대기 상태로 전환된 것으로 추정";
}

function renderMemories(memories, demoted = []) {
  const host = byId("memoryList");
  byId("memoryCount").textContent = memories.length;
  const memoryHtml = memories.map((memory) => {
    const confidence = Math.round(memory.confidence * 100);
    const symbol = gestureSymbols[memory.gesture_key] || "?";
    return `<article class="memory-item">
      <div class="memory-top">
        <span class="memory-symbol">${symbol}</span>
        <div><strong>${intentLabel(memory.intent)}</strong><small>${memory.motion_type} / ${memory.direction} / ${memory.observation_count} observations</small></div>
        <span class="context-chip">${memory.context_scope}</span>
      </div>
      <div class="memory-confidence"><span>${confidence}%</span><div class="bar"><i style="width:${confidence}%"></i></div></div>
    </article>`;
  }).join("");
  const demotedHtml = demoted.length ? `
    <div class="memory-demoted-heading">자동 강등 추정 (${demoted.length})</div>
    ${demoted.map((candidate) => {
      const confidence = Math.round(candidate.confidence * 100);
      const symbol = gestureSymbols[candidate.gesture_key] || "?";
      return `<article class="memory-item demoted">
        <div class="memory-top">
          <span class="memory-symbol">${symbol}</span>
          <div><strong>${intentLabel(candidate.intent)}</strong><small>${candidate.motion_type} / ${candidate.direction} / ${candidate.observation_count} observations</small></div>
          <span class="context-chip">${candidate.context_scope}</span>
        </div>
        <div class="memory-confidence"><span>${confidence}%</span><div class="bar"><i style="width:${confidence}%"></i></div></div>
        <p class="demoted-reason">${inferDemotionReason(candidate)}</p>
      </article>`;
    }).join("")}` : "";
  host.innerHTML = memoryHtml || demotedHtml
    ? memoryHtml + demotedHtml
    : `<div class="empty-state small"><p>아직 기억된 몸짓이 없습니다.</p></div>`;
}

function renderInterpretations(memories) {
  const host = byId("interpretationList");
  const filtered = memories.filter((memory) => memory.context_scope === currentContext);
  if (!filtered.length) {
    host.innerHTML = `<div class="empty-mini">이 상황에서 학습된 몸짓이 아직 없습니다.</div>`;
    return;
  }
  host.innerHTML = filtered.map((memory) => `
    <div class="interpretation-item">
      <span class="symbol">${gestureSymbols[memory.gesture_key] || "?"}</span>
      <div><strong>${memory.motion_type} / ${memory.direction}</strong><small>→ ${intentLabel(memory.intent)}</small></div>
      <em>${Math.round(memory.confidence * 100)}%</em>
    </div>`).join("");
}

function renderEvents(events) {
  const host = byId("eventList");
  if (!events.length) {
    host.innerHTML = `<div class="empty-mini">이벤트를 기다리는 중입니다.</div>`;
    return;
  }
  host.innerHTML = events.map((event) => {
    const date = new Date(event.time);
    const time = Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return `<div class="event-item" data-type="${event.type}" data-status="${event.status || ""}"><span class="event-dot"></span><div><strong>${intentLabel(event.title)}</strong><small>${event.detail}</small></div><time>${time}</time></div>`;
  }).join("");
}

const feedbackLabels = {
  CORRECT: "맞아요",
  WRONG_ACTION: "아니에요",
  ACCIDENTAL_GESTURE: "의도치 않은 몸짓",
  IGNORE: "무시",
};

function renderExecutionAudit(entries = []) {
  const host = byId("auditList");
  if (!entries.length) {
    host.innerHTML = `<div class="empty-mini">자동 실행된 기록이 아직 없습니다.</div>`;
    return;
  }
  host.innerHTML = entries.map((entry) => {
    const date = new Date(entry.executed_at);
    const time = Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const symbol = gestureSymbols[entry.gesture_key] || "?";
    const confidence = Math.round(entry.confidence * 100);
    const reason = entry.status === "FAILED"
      ? (entry.error_message || "동작을 전달하지 못했습니다.")
      : `${entry.context_scope} · ${entry.motion_type}/${entry.direction} · ${entry.execution_mode}`;
    const feedback = entry.feedback_type
      ? `<span class="audit-feedback" data-feedback="${entry.feedback_type}">${feedbackLabels[entry.feedback_type] || entry.feedback_type}</span>`
      : `<span>피드백 대기</span>`;
    return `<article class="audit-item" data-status="${entry.status}">
      <div class="audit-top">
        <span class="audit-symbol">${symbol}</span>
        <div><strong>${intentLabel(entry.intent)}</strong><small>${reason}</small></div>
        <span class="audit-confidence">${confidence}%</span>
      </div>
      <div class="audit-meta"><span>${time}</span>${feedback}</div>
    </article>`;
  }).join("");
}

async function refreshDashboard() {
  if (dashboardRequest) return dashboardRequest;
  dashboardRequest = loadDashboard();
  try {
    return await dashboardRequest;
  } finally {
    dashboardRequest = null;
  }
}

async function loadDashboard() {
  try {
  const state = await request(`/dashboard?user_id=${encodeURIComponent(USER_ID)}`);
  dashboardState = state;
  // The in-browser camera stream is authoritative when it's running locally;
  // otherwise fall back to detecting the separate Python webcam client from
  // the space it stamps on observations.
  const fromWebcam = Boolean(cameraStream) || state.context?.space === "camera_demo";
  const modePill = byId("inputModePill");
  modePill.textContent = fromWebcam ? "웹캠 실시간 감지" : "버튼 시뮬레이션";
  modePill.dataset.source = fromWebcam ? "webcam" : "button";
  byId("metricObservations").textContent = state.counts.observations;
  byId("metricMemories").textContent = state.counts.learned_memories;
  byId("metricPending").textContent = state.counts.pending_suggestions;
  renderSuggestions(state.suggestions, state.candidates);
  // Exclude candidates still awaiting their first suggestion decision - only
  // ones that reached the threshold with no pending suggestion can only have
  // gotten there via a prior ACTIVE/rejected state, i.e. an actual demotion.
  const pendingPatternIds = new Set(state.suggestions.map((suggestion) => suggestion.gesture_pattern_id));
  const demoted = state.candidates.filter((candidate) => candidate.observation_count >= state.threshold
    && !pendingPatternIds.has(candidate.id));
  renderMemories(state.memories, demoted);
  renderInterpretations(state.memories);
  renderEvents(state.events);
  renderExecutionAudit(state.execution_audit);
  const candidate = state.candidates.find((item) => item.context_scope === currentContext);
  byId("learningProgress").textContent = candidate
    ? `${Math.min(candidate.observation_count, state.threshold)}/${state.threshold}`
    : `0/${state.threshold}`;
  byId("dashboardConnection").hidden = true;
  } catch (error) {
    byId("dashboardConnection").hidden = false;
    throw error;
  }
}

// The webcam client posts to the API directly, so state can change without any
// request from this tab. Poll while the tab is visible and idle.
// ponytail: polling, not SSE - one demo user, one tab, 3s is invisible here.
function startAutoRefresh() {
  const poll = () => {
    if (document.hidden) return;
    if (byId("actionOverlay").open) return;
    if (document.querySelector("[aria-busy='true']")) return;
    refreshDashboard().catch(() => {});
  };
  window.setInterval(poll, 3000);
  // Browsers throttle timers in a background tab, so catch up the moment the
  // tab is looked at again rather than waiting out the throttled interval.
  document.addEventListener("visibilitychange", poll);
}

async function resetDemo() {
  const button = byId("resetButton");
  button.textContent = "초기화 중…";
  await withBusy([button], async () => {
    try {
      await post("/demo/reset");
      lastObservation = null;
      lastExecution = null;
      updateTeachingCard("먼저 몸짓을 발생시켜 주세요", "학습 전에는 아무 동작도 자동 실행하지 않습니다.");
      setAgentState(
        "",
        "몸짓을 자연스럽게\n사용해 보세요",
        "별도의 제스처를 외울 필요가 없습니다. AI가 반복되는 행동과 맥락을 관찰합니다.",
      );
      renderActionButtons();
      await refreshDashboard();
    } catch (error) {
      showToast(`초기화 실패: ${error.message}`);
      button.dataset.state = "error";
    }
  });
  button.textContent = "초기화";
}

async function loadPrivacy() {
  try {
    const privacy = await request("/demo/privacy");
    const items = byId("privacyChecklist").children;
    const flags = [privacy.raw_video_stored, privacy.face_recognition_used, privacy.cloud_video_uploaded];
    flags.forEach((on, index) => {
      const label = items[index].firstChild;
      const value = items[index].querySelector("strong");
      label.textContent = label.textContent.trim();
      value.textContent = on ? "ON" : "OFF";
      value.dataset.on = String(on);
    });
    byId("privacyNote").textContent = `${privacy.processing_mode} — ${privacy.note}`;
  } catch (_) {
    // Keep the static OFF/OFF/OFF defaults baked into the markup.
  }
}

function applyBootstrapConfig(bootstrap) {
  intentLabels = bootstrap.intent_labels;
  autoExecutionThreshold = bootstrap.auto_execution_threshold;
  osActionsEnabled = bootstrap.os_actions_enabled;
  demoModeEnabled = bootstrap.demo_mode;

  const thresholdPct = Math.round(autoExecutionThreshold * 100);
  byId("memoryPanelDescription").textContent = `승인된 연결만 자동 실행합니다 (신뢰도 ${thresholdPct}% 이상).`;

  const osModeBadge = byId("osModeBadge");
  osModeBadge.textContent = osActionsEnabled ? "실제 키 입력 활성" : "시뮬레이션 모드";
  osModeBadge.dataset.live = String(osActionsEnabled);

  const resetButton = byId("resetButton");
  resetButton.disabled = !demoModeEnabled;
  resetButton.title = demoModeEnabled ? "" : "데모 모드가 아니어서 초기화를 사용할 수 없습니다.";
}

async function init() {
  try {
    applyBootstrapConfig(await post("/demo/bootstrap"));
    renderContext();
    await refreshDashboard();
  } catch (error) {
    showToast(`서버 연결 실패: ${error.message}`);
    byId("dashboardConnection").hidden = false;
  }
  loadPrivacy();

  startAutoRefresh();
  byId("retryDashboard").addEventListener("click", () => refreshDashboard().catch(() => {}));

  all(".segment").forEach((button) => {
    button.addEventListener("click", () => {
      currentContext = button.dataset.context;
      lastObservation = null;
      renderContext();
      refreshDashboard().catch(() => {});
      updateTeachingCard("상황이 변경되었습니다", `${contextDefinitions[currentContext].title} 맥락에서 몸짓을 관찰합니다.`);
      setAgentState(
        "",
        `${contextDefinitions[currentContext].title} 상황을 이해하고 있어요`,
        "같은 몸짓도 현재 앱과 행동에 따라 다른 의도로 해석합니다.",
      );
    });
  });
  all(".gesture-button").forEach((button) => {
    button.addEventListener("click", () => observeGesture(button));
  });
  byId("startCameraButton").addEventListener("click", startCamera);
  byId("stopCameraButton").addEventListener("click", stopCamera);
  byId("cameraDeviceSelect").addEventListener("change", () => changeCameraDevice().catch((error) => {
    setCameraStatus(`입력 장치를 바꾸지 못했습니다: ${error.message}`, "error");
  }));
  byId("resetButton").addEventListener("click", resetDemo);
  all("[data-feedback]").forEach((button) => {
    button.addEventListener("click", () => submitFeedback(button.dataset.feedback));
  });
  byId("actionOverlay").addEventListener("click", (event) => {
    if (event.target.id !== "actionOverlay") return;
    const rect = event.currentTarget.getBoundingClientRect();
    const isOutside = event.clientX < rect.left || event.clientX > rect.right
      || event.clientY < rect.top || event.clientY > rect.bottom;
    if (isOutside) closeActionOverlay();
  });
  byId("actionOverlay").addEventListener("close", () => {
    lastGestureButton?.focus({ preventScroll: true });
  });

  byId("tutorialButton").addEventListener("click", openTutorial);
  byId("tutorialSkip").addEventListener("click", closeTutorial);
  byId("tutorialPrev").addEventListener("click", () => {
    tutorialSlideIndex = Math.max(0, tutorialSlideIndex - 1);
    renderTutorialSlide();
  });
  byId("tutorialNext").addEventListener("click", () => {
    if (tutorialSlideIndex === TUTORIAL_SLIDE_COUNT - 1) return closeTutorial();
    tutorialSlideIndex += 1;
    renderTutorialSlide();
  });
  byId("tutorialOverlay").addEventListener("click", (event) => {
    if (event.target.id !== "tutorialOverlay") return;
    const rect = event.currentTarget.getBoundingClientRect();
    const isOutside = event.clientX < rect.left || event.clientX > rect.right
      || event.clientY < rect.top || event.clientY > rect.bottom;
    if (isOutside) closeTutorial();
  });
  // Runs on every close path (button, backdrop click, Esc) so the checkbox
  // is honored even when the native dialog closes itself on Escape.
  byId("tutorialOverlay").addEventListener("close", () => {
    if (!byId("tutorialHideToday").checked) return;
    try {
      window.localStorage.setItem(TUTORIAL_HIDE_KEY, todayKey());
    } catch (_) {
      // Storage unavailable (e.g. private browsing) - just skip persisting.
    }
  });
  if (!isTutorialHiddenToday()) openTutorial();
}

document.addEventListener("DOMContentLoaded", init);
window.addEventListener?.("pagehide", stopCamera);
