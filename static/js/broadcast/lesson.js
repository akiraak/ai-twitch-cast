// 授業表示ハンドラ（C# LessonPlayer → WebView2 JS interop）
//
// C#が ExecuteScriptAsync 経由で以下を呼ぶ:
//   window.lesson.showText(text, displayProperties)
//   window.lesson.hideText()
//   window.lesson.startDialogue({content, speaker, avatarId, emotion, gesture, lipsyncFrames, duration})
//   window.lesson.endDialogue()
//   window.lesson.pause()
//   window.lesson.resume()

// 感情→BlendShapeのデフォルトマッピング（キャラクター設定のfallback）
const _EMOTION_BLENDSHAPES = {
  joy:         { happy: 1.0 },
  excited:     { happy: 0.7 },
  surprise:    { happy: 0.5 },
  thinking:    { sad: 0.3 },
  sad:         { sad: 0.6 },
  embarrassed: { happy: 0.4, sad: 0.2 },
  neutral:     {},
};

// すべてのBlendShapeキーを収集（リセット用）
const _ALL_BLEND_KEYS = new Set();
for (const shapes of Object.values(_EMOTION_BLENDSHAPES)) {
  for (const k of Object.keys(shapes)) _ALL_BLEND_KEYS.add(k);
}

let _currentAvatarId = null;
let _paused = false;

// === タイムライン状態 ===
const _timelineState = {
  lessonId: 0,
  sections: [],            // outline 由来
  currentSection: -1,      // 再生中セクション
  currentDialogue: -1,     // 再生中 dialogue index
  currentKind: 'main',     // 'main' | 'answer'
  viewSection: -1,         // 表示中のタブ（手動選択中は currentSection と異なる）
  autoFollow: true,
  followTimer: null,
};
const _FOLLOW_RESET_MS = 5000;

function _getAvatar(avatarId) {
  return window.avatarInstances?.[avatarId];
}

window.lesson = {
  showText(text, displayProperties) {
    showLessonText(text, displayProperties || null);
  },

  hideText() {
    hideLessonText();
  },

  // outline受信: 全セクションのdialogue一覧をまとめて設定
  setOutline(outline) {
    _timelineState.lessonId = outline.lesson_id || 0;
    _timelineState.sections = Array.isArray(outline.sections) ? outline.sections : [];
    _timelineState.currentSection = -1;
    _timelineState.currentDialogue = -1;
    _timelineState.currentKind = 'main';
    _timelineState.autoFollow = true;
    _timelineState.viewSection = _timelineState.sections.length > 0 ? 0 : -1;
    if (typeof showLessonDialogues === 'function') showLessonDialogues();
    console.log(`[lesson] setOutline: sections=${_timelineState.sections.length}, lesson_id=${_timelineState.lessonId}`);
  },

  // 授業完了: 全行past化
  onComplete(data) {
    _timelineState.currentSection = -1;
    _timelineState.currentDialogue = -1;
    if (typeof renderLessonDialogues === 'function') renderLessonDialogues();
    console.log(`[lesson] onComplete: reason=${data?.reason}`);
  },

  startDialogue(data) {
    const avatarId = data.avatarId || 'teacher';
    _currentAvatarId = avatarId;
    const avatar = _getAvatar(avatarId);

    // タイムライン更新（sectionIndex/dialogueIndex/kind が付与されていれば）
    if (typeof data.sectionIndex === 'number' && typeof data.dialogueIndex === 'number') {
      _timelineState.currentSection = data.sectionIndex;
      _timelineState.currentDialogue = data.dialogueIndex;
      _timelineState.currentKind = data.kind || 'main';
      if (_timelineState.autoFollow) {
        _timelineState.viewSection = data.sectionIndex;
      }
      if (typeof renderLessonDialogues === 'function') renderLessonDialogues();
    }

    // 1. 感情BlendShape適用
    const blendshapes = data.blendshapes
      || _EMOTION_BLENDSHAPES[data.emotion]
      || {};
    if (avatar) {
      avatar.setBlendShapes(blendshapes);
    }

    // 2. ジェスチャー
    if (data.gesture && avatar) {
      avatar.playGesture(data.gesture);
    }

    // 3. 字幕表示（showSubtitle のデータ形式に変換）
    showSubtitle({
      avatar_id: avatarId,
      trigger_text: '',
      translation: '',
      speech: data.content || '',
      duration: data.duration || 5,
    });

    // 4. リップシンク開始
    if (data.lipsyncFrames && avatar) {
      avatar.setLipsync(data.lipsyncFrames);
      avatar.startLipsync();
    }

    console.log(`[lesson] startDialogue: speaker=${data.speaker}, avatar=${avatarId}, emotion=${data.emotion}, duration=${data.duration}`);
  },

  endDialogue() {
    const avatarId = _currentAvatarId || 'teacher';
    const avatar = _getAvatar(avatarId);

    // 1. リップシンク停止
    if (avatar) {
      avatar.stopLipsync();
    }

    // 2. 字幕フェード
    fadeSubtitle(avatarId);

    // 3. 感情リセット（全BlendShapeを0に）
    if (avatar) {
      const reset = {};
      for (const k of _ALL_BLEND_KEYS) reset[k] = 0.0;
      avatar.setBlendShapes(reset);
    }

    _currentAvatarId = null;
    console.log(`[lesson] endDialogue: avatar=${avatarId}`);
  },

  pause() {
    _paused = true;
    // リップシンク一時停止（フレーム進行を停止）
    const avatar = _getAvatar(_currentAvatarId || 'teacher');
    if (avatar) {
      avatar.stopLipsync();
    }
    console.log('[lesson] paused');
  },

  resume() {
    _paused = false;
    console.log('[lesson] resumed');
  },
};
