import cv2, numpy as np, time, sys, requests

API = 'http://127.0.0.1:8000/api/v1'

def post(path, payload):
    try:
        r = requests.post(f'{API}{path}', json=payload, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'API_ERROR: {e}')
        return None

print('Webcam client (max|dx| based) starting...')
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print('CAMERA_FAIL'); sys.exit(1)

print('CAMERA_OK. Move hand horizontally inside guide.')
prev_gray = None
last_detection = 0.0
latest_obs_id = None
detection_count = 0

boot = post('/demo/bootstrap', {})
if not boot:
    print('Warning: bootstrap failed')

try:
    while True:
        ok, frame = cap.read()
        if not ok:
            print('FRAME_READ_FAIL'); break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        x1, y1 = int(w*0.18), int(h*0.20)
        x2, y2 = int(w*0.82), int(h*0.82)
        roi = frame[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7,7), 0)

        detected = False
        direction = None
        max_abs_dx = 0.0
        moving_ratio = 0.0
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 21, 3, 5, 1.2, 0)
            dx = flow[..., 0]
            max_abs_dx = float(np.max(np.abs(dx)))
            motion_mask = np.abs(dx) > 1.0
            moving_ratio = float(np.mean(motion_mask))
            now = time.time()
            if moving_ratio > 0.01 and now - last_detection > 1.2:
                mean_dx_on_motion = float(np.mean(dx[motion_mask])) if motion_mask.any() else 0.0
                if abs(mean_dx_on_motion) > 0.3:
                    direction = 'right' if mean_dx_on_motion > 0 else 'left'
                    detected = True
                    last_detection = now
                    detection_count += 1
                    print(f'DETECTED: {direction} (max|dx|={max_abs_dx:.2f}, moving_ratio={moving_ratio:.1%}) #{detection_count}')

                    payload = {
                        'user_id': 'demo-user',
                        'context': {'active_app': 'PowerPoint', 'activity': 'presentation', 'space': 'camera_demo', 'device': 'laptop'},
                        'gesture': {'motion_type': 'swipe', 'direction': direction, 'duration_ms': 430},
                        'attempt_inference': True,
                    }
                    result = post('/observe', payload)
                    if result:
                        latest_obs_id = result['observation']['id']
                        inf = result['inference']
                        if inf['matched']:
                            print(f'  => {inf["intent"]} (confidence={inf["confidence"]:.2f})')
                        else:
                            print(f'  => No match (try N/B to teach action)')
                    else:
                        print('  => observe POST failed')

        prev_gray = gray
        cv2.rectangle(frame, (x1,y1), (x2,y2), (104,224,255), 2)
        status = f' detections: {detection_count}'
        if direction:
            status += f' | last: {direction}'
        cv2.putText(frame, f'SilentOrchestra 2.0 - Local Optical Flow{status}', (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        cv2.putText(frame, 'Q quit | N next action | B prev action | Space play/pause', (16, h-16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220,220,220), 1)
        cv2.imshow('SilentOrchestra 2.0 - Local Optical Flow', frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print('QUIT by user')
            break
        elif key in (ord('n'), ord('b'), ord(' ')) and latest_obs_id:
            intent_map = {
                ord('n'): ('NEXT_SLIDE', 'powerpoint'),
                ord('b'): ('PREVIOUS_SLIDE', 'powerpoint'),
                ord(' '): ('TOGGLE_PLAYBACK', 'media_player'),
            }
            intent, target = intent_map[key]
            result = post('/teach', {
                'user_id': 'demo-user',
                'observation_id': latest_obs_id,
                'action_type': intent,
                'target': target,
                'parameters': {},
            })
            if result:
                print(f'TEACH: {intent} -> {target} ({result["progress_current"]}/{result["progress_required"]})')
                if result.get('suggestion'):
                    print(f'  SUGGESTION_READY: {result["suggestion"]["id"]}')
            latest_obs_id = None
finally:
    cap.release()
    cv2.destroyAllWindows()
    print('Released camera.')
