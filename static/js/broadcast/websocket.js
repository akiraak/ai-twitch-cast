// WebSocket接続（統合: overlay + tts + bgm）

// avatar_id に基づきアバターインスタンスを取得
function getAvatar(avatarId) {
  return window.avatarInstances?.[avatarId];
}

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${location.host}/ws/broadcast`);
  window._ws = ws;  // グローバル参照（C# JS注入からの音量保存用）

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);

    switch (data.type) {
      // オーバーレイイベント
      case 'comment':
        _pendingSubtitle = data;
        if (!_isStreaming) { showSubtitle(data); }
        // 配信時は lipsync と同時に遅延表示（下の lipsync case で処理）
        // C#パネルにコメント転送
        if (window.chrome?.webview) {
          window.chrome.webview.postMessage({ _comment: data });
        }
        break;
      case 'speaking_end':
        fadeSubtitle(data.avatar_id || _pendingSubtitle?.avatar_id);
        break;
      case 'settings_update':
        if (!_saving) {
          applySettings(data);
          // customtext/captureアイテムの共通プロパティ適用
          for (const [key, val] of Object.entries(data)) {
            if (typeof val !== 'object' || key === 'type') continue;
            if (key.startsWith('customtext:')) {
              const id = parseInt(key.split(':')[1]);
              const el = customTextLayers[id];
              if (el) {
                applyCommonStyle(el, val);
                if (val.content != null) {
                  const ct = el.querySelector('.custom-text-content');
                  if (ct) { ct.dataset.rawContent = val.content; ct.textContent = replaceTextVariables(val.content); }
                }
              }
            } else if (key.startsWith('capture:')) {
              const id = key.split(':')[1];
              const el = captureLayers[id];
              if (el) applyCommonStyle(el, val);
            } else if (key.startsWith('child:')) {
              const el = childPanelEls[key];
              if (el) applyCommonStyle(el, val);
            }
          }
        }
        break;

      // サーバー再起動 → ページリロード（HTML/JS更新を反映）
      case 'server_restart':
        console.log('[WS] server_restart received, reloading...');
        setTimeout(() => location.reload(), 500);
        return;

      // 配信状態（リップシンク遅延切替用）
      case 'stream_status':
        _isStreaming = !!data.streaming;
        console.log('[Sync] streaming:', _isStreaming);
        break;

      // 音声はすべてC#アプリが再生（play_audio / bgm_play / bgm_stop はブラウザ不使用）

      // 音量制御（C#アプリに転送）
      case 'volume':
        if (data.source && data.volume != null) {
          volumes[data.source] = data.volume;
          applyVolume();
        }
        break;


      // VRMアバター制御（avatar_id でルーティング）
      case 'blendshape': {
        const avatar = getAvatar(data.avatar_id);
        if (avatar && data.shapes) avatar.setBlendShapes(data.shapes);
        if (avatar && data.gesture) avatar.playGesture(data.gesture);
        break;
      }
      case 'lipsync': {
        const avatar = getAvatar(data.avatar_id);
        if (avatar && data.frames) {
          const delay = _isStreaming ? _lipsyncDelay : 0;
          avatar.setLipsync(data.frames);
          clearTimeout(_syncTimer);
          if (delay > 0) {
            _syncTimer = setTimeout(() => {
              if (_pendingSubtitle) { showSubtitle(_pendingSubtitle); _pendingSubtitle = null; }
              avatar.startLipsync();
            }, delay);
          } else {
            avatar.startLipsync();
          }
          console.log(`[Sync] lipsync: avatar=${data.avatar_id}, ${data.frames.length} frames, delay=${delay}ms`);
        }
        break;
      }
      case 'lipsync_stop': {
        const avatar = getAvatar(data.avatar_id);
        if (avatar) avatar.stopLipsync();
        break;
      }

      // 生徒アバター表示/非表示
      case 'student_avatar_show': {
        const area = document.getElementById('avatar-area-2');
        if (area) area.style.display = 'block';
        const student = window.avatarInstances?.['student'];
        if (student && data.vrm) {
          student.loadVRM(`/resources/vrm/${data.vrm}`);
        }
        break;
      }
      case 'student_avatar_hide': {
        const area = document.getElementById('avatar-area-2');
        if (area) area.style.display = 'none';
        break;
      }

      // アバターストリーム（MJPEG fallback）
      case 'avatar_stream':
        setAvatarStream(data.url);
        break;
      case 'avatar_stop':
        stopAvatarStream();
        break;

      // TODO更新（WebSocket push）
      case 'todo_update':
        renderTodoItems(data.items || []);
        break;

      // ウィンドウキャプチャ
      case 'capture_add':
        addCaptureLayer(data.id, data.stream_url, data.label, data.layout);
        break;
      case 'capture_remove':
        removeCaptureLayer(data.id);
        break;
      case 'capture_layout':
        updateCaptureLayout(data.id, data.layout);
        break;

      // カスタムテキスト
      case 'custom_text_add':
        addCustomTextLayer(data.id, data.label, data.content, data.layout);
        break;
      case 'custom_text_update':
        updateCustomTextLayer(data.id, data);
        break;
      case 'custom_text_remove':
        removeCustomTextLayer(data.id);
        break;

      // 子パネル
      case 'child_panel_add':
        addChildPanel(data.parentId, data);
        break;
      case 'child_panel_remove':
        removeChildPanel(data.id);
        break;

      // 授業テキスト
      case 'lesson_text_show':
        showLessonText(data.text, data.display_properties);
        break;
      case 'lesson_text_hide':
        hideLessonText();
        break;

      // 授業ステータス（パネル表示切替 + タイトル + 進捗パネル更新）
      case 'lesson_status':
        if (data.state === 'running' || data.state === 'paused') {
          setLessonMode(true);
          if (data.lesson_name) {
            showLessonTitle(data.lesson_name);
          }
          if (data.sections) {
            showLessonProgress(data.sections, data.current_index);
          } else {
            updateLessonProgress(data.current_index);
          }
        } else {
          setLessonMode(false);
        }
        break;

      // 素材変更
      case 'avatar_vrm_change':
        if (data.url) loadVRM(data.url);
        break;
      case 'avatar2_vrm_change':
        if (data.url && window.avatarInstances?.['student']) {
          window.avatarInstances['student'].loadVRM(data.url);
        }
        break;
      case 'background_change':
        if (data.url) document.getElementById('background').src = data.url;
        break;
    }
  };

  ws.onclose = () => { window._ws = null; setTimeout(connectWS, 3000); };
  ws.onerror = () => ws.close();
}
