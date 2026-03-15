const topicInput = document.getElementById("topic");
const sourceText = document.getElementById("sourceText");
const fileInput = document.getElementById("fileInput");
const fileStatus = document.getElementById("fileStatus");
const questionCountInput = document.getElementById("questionCount");
const modeInput = document.getElementById("mode");
const difficultyInput = document.getElementById("difficulty");
const openTimerMinutesInput = document.getElementById("openTimerMinutes");
const generateBtn = document.getElementById("generateBtn");
const clearBtn = document.getElementById("clearBtn");
const result = document.getElementById("result");

const livePreviewTopic = document.getElementById("livePreviewTopic");
const livePreviewText = document.getElementById("livePreviewText");
const chipQuestions = document.getElementById("chipQuestions");
const chipTest = document.getElementById("chipTest");
const chipMixed = document.getElementById("chipMixed");

const sessionContainer = document.getElementById("sessionContainer");
const sessionTitle = document.getElementById("sessionTitle");
const sessionInfo = document.getElementById("sessionInfo");
const sessionModeInfo = document.getElementById("sessionModeInfo");
const localLinkInput = document.getElementById("localLink");
const shareLinkInput = document.getElementById("shareLink");
const copyLocalLinkBtn = document.getElementById("copyLocalLinkBtn");
const copyShareLinkBtn = document.getElementById("copyShareLinkBtn");
const toggleEditBtn = document.getElementById("toggleEditBtn");
const saveEditsBtn = document.getElementById("saveEditsBtn");
const downloadTestPdfBtn = document.getElementById("downloadTestPdfBtn");
const downloadResultsPdfBtn = document.getElementById("downloadResultsPdfBtn");

let currentSessionPayload = null;
let editMode = false;
let openQuestionTimerInterval = null;
let openQuestionTimeLeft = 0;

function updatePreview() {
  if (livePreviewTopic && topicInput) {
    const value = topicInput.value.trim();
    livePreviewTopic.textContent = value ? `Тест по теме: ${value}` : "Тест по теме: Информатика";
  }

  if (livePreviewText && sourceText) {
    const text = sourceText.value.trim();
    if (text) {
      const shortText = text.length > 110 ? text.slice(0, 110) + "..." : text;
      livePreviewText.textContent = shortText;
    } else {
      livePreviewText.textContent =
        "Система автоматически создает вопросы и тесты на основе введенных данных.";
    }
  }

  if (modeInput) {
    chipQuestions?.classList.remove("chip-active");
    chipTest?.classList.remove("chip-active");
    chipMixed?.classList.remove("chip-active");

    if (modeInput.value === "questions") chipQuestions?.classList.add("chip-active");
    if (modeInput.value === "test") chipTest?.classList.add("chip-active");
    if (modeInput.value === "mixed") chipMixed?.classList.add("chip-active");
  }
}

async function handleFileUpload(file) {
  if (!file) return;

  if (fileStatus) {
    fileStatus.textContent = "Файл загружается...";
    fileStatus.className = "hint loading-text";
  }

  try {
    const extension = file.name.split(".").pop().toLowerCase();
    let extractedText = "";

    if (extension === "txt") {
      extractedText = await readTxtFile(file);
    } else if (extension === "pdf") {
      extractedText = await readPdfFile(file);
    } else if (extension === "docx") {
      extractedText = await readDocxFile(file);
    } else {
      throw new Error("Неподдерживаемый формат файла");
    }

    sourceText.value = extractedText.trim();

    if (fileStatus) {
      fileStatus.textContent = `Файл успешно обработан: ${file.name}`;
      fileStatus.className = "hint";
    }

    updatePreview();
  } catch (error) {
    if (fileStatus) {
      fileStatus.textContent = `Ошибка обработки файла: ${error.message}`;
      fileStatus.className = "hint error-text";
    }
  }
}

function readTxtFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target.result || "");
    reader.onerror = () => reject(new Error("Не удалось прочитать TXT-файл"));
    reader.readAsText(file, "UTF-8");
  });
}

async function readPdfFile(file) {
  if (!window.pdfjsLib) {
    throw new Error("PDF библиотека не подключена");
  }

  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  let text = "";

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const textContent = await page.getTextContent();
    text += textContent.items.map((item) => item.str).join(" ") + "\n";
  }

  return text;
}

async function readDocxFile(file) {
  if (!window.mammoth) {
    throw new Error("DOCX библиотека не подключена");
  }

  const arrayBuffer = await file.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer });
  return result.value || "";
}

if (topicInput) topicInput.addEventListener("input", updatePreview);
if (sourceText) sourceText.addEventListener("input", updatePreview);
if (modeInput) modeInput.addEventListener("change", updatePreview);

if (fileInput) {
  fileInput.addEventListener("change", async function (event) {
    const file = event.target.files[0];
    await handleFileUpload(file);
  });
}

if (clearBtn) {
  clearBtn.addEventListener("click", function () {
    topicInput.value = "";
    sourceText.value = "";
    fileInput.value = "";
    questionCountInput.value = 10;
    modeInput.value = "questions";
    difficultyInput.value = "medium";
    openTimerMinutesInput.value = 10;

    if (result) {
      result.innerHTML = `<p class="empty-text">После генерации произойдет переход на отдельную страницу результата.</p>`;
    }

    if (fileStatus) {
      fileStatus.textContent = "";
      fileStatus.className = "hint";
    }

    updatePreview();
  });
}

if (generateBtn) {
  generateBtn.addEventListener("click", function () {
    const topic = topicInput.value.trim();
    const text = sourceText.value.trim();
    const count = Math.max(1, Math.min(300, Number(questionCountInput.value) || 10));
    const mode = modeInput.value;
    const difficulty = difficultyInput.value;
    const openTimerMinutes = Math.max(1, Math.min(180, Number(openTimerMinutesInput.value) || 10));

    if (!topic && !text) {
      result.innerHTML =
        `<p class="empty-text" style="color:#dc2626;">Введите тему или текст для генерации.</p>`;
      return;
    }

    const source = text || topic;
    const allQuestionCandidates = generateQuestionsWithAnswers(topic, source, Math.max(count * 3, count), difficulty);
    const selectedQuestions = allQuestionCandidates.slice(0, count);

    const payload = {
      id: generateId(),
      topic: topic || "Без названия",
      mode,
      difficulty,
      sourceText: source,
      openTimerMinutes,
      createdAt: new Date().toISOString(),
      questions: selectedQuestions,
      test: generateRandomTest(allQuestionCandidates, source, count),
      openResults: [],
      testResults: null
    };

    localStorage.setItem(`masterTest_${payload.id}`, JSON.stringify(payload));
    localStorage.setItem("masterTest_last", payload.id);

    window.location.href = `session.html?id=${encodeURIComponent(payload.id)}`;
  });
}

function splitIntoSentences(text) {
  return String(text)
    .replace(/\n+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 25);
}

function getKeywords(text) {
  const stopWords = new Set([
    "это", "как", "что", "для", "при", "или", "его", "ее", "они", "она", "оно",
    "мы", "вы", "ты", "также", "если", "когда", "были", "было", "есть", "быть",
    "из", "на", "в", "во", "не", "по", "с", "со", "к", "до", "от", "за", "у",
    "о", "об", "а", "но", "и", "то", "же", "ли", "этот", "эта", "эти", "такой",
    "также", "который", "которая", "которые", "является", "являются"
  ]);

  const words = String(text)
    .toLowerCase()
    .replace(/[^а-яa-z0-9ё\s-]/gi, " ")
    .split(/\s+/)
    .filter((word) => word.length > 4 && !stopWords.has(word));

  const frequency = {};
  words.forEach((word) => {
    frequency[word] = (frequency[word] || 0) + 1;
  });

  return Object.keys(frequency)
    .sort((a, b) => frequency[b] - frequency[a])
    .slice(0, 80);
}

function cleanFragment(text, maxLen = 170) {
  const value = String(text).replace(/\s+/g, " ").trim();
  if (value.length <= maxLen) return value;
  return value.slice(0, maxLen).trim() + "...";
}

function generateQuestionsWithAnswers(topic, text, count, difficulty) {
  const items = [];
  const sentences = splitIntoSentences(text);
  const keywords = getKeywords(text || topic);

  // Вопросы по предложениям из файла/текста
  sentences.forEach((sentence) => {
    const fragment = cleanFragment(sentence);
    let question = "";

    if (difficulty === "easy") {
      question = `О чем говорится в следующем фрагменте: «${fragment}»?`;
    } else if (difficulty === "medium") {
      question = `Какую основную мысль передает следующий фрагмент: «${fragment}»?`;
    } else {
      question = `Поясните смысл следующего фрагмента: «${fragment}».`;
    }

    items.push({
      question,
      correctAnswer: sentence,
      sourceType: "sentence"
    });
  });

  // Вопросы по ключевым словам из текста/файла
  keywords.forEach((keyword) => {
    let question = "";

    if (difficulty === "easy") {
      question = `Что означает понятие «${keyword}»?`;
    } else if (difficulty === "medium") {
      question = `Как связано понятие «${keyword}» с темой текста?`;
    } else {
      question = `Почему понятие «${keyword}» важно для понимания темы?`;
    }

    items.push({
      question,
      correctAnswer: keyword,
      sourceType: "keyword"
    });
  });

  if (items.length === 0) {
    for (let i = 0; i < count; i++) {
      const fallback = topic || `тема ${i + 1}`;
      items.push({
        question: `Что можно сказать по теме «${fallback}»?`,
        correctAnswer: fallback,
        sourceType: "fallback"
      });
    }
  }

  return uniqueByQuestion(items);
}

function uniqueByQuestion(items) {
  const seen = new Set();
  const result = [];

  items.forEach((item) => {
    const key = item.question.trim().toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(item);
    }
  });

  return result;
}

function generateRandomTest(questionItems, sourceText, count) {
  const keywords = getKeywords(sourceText);
  const pool = [...questionItems];
  shuffleInPlace(pool);

  const selected = pool.slice(0, Math.min(count, pool.length));

  const testItems = selected.map((item, index) => {
    const correctAnswer = item.correctAnswer;
    const distractors = buildDistractors(keywords, questionItems, correctAnswer, index);
    const options = shuffleArray([correctAnswer, ...distractors.slice(0, 3)]);

    return {
      question: item.question,
      correctAnswer,
      options
    };
  });

  shuffleInPlace(testItems);
  return testItems;
}

function buildDistractors(keywords, questionItems, correctAnswer, index) {
  const pool = [];

  keywords.forEach((k) => {
    if (normalizeText(k) !== normalizeText(correctAnswer)) {
      pool.push(k);
    }
  });

  questionItems.forEach((item) => {
    if (item.correctAnswer && normalizeText(item.correctAnswer) !== normalizeText(correctAnswer)) {
      pool.push(item.correctAnswer);
    }
  });

  splitIntoSentences(correctAnswer).forEach((fragment) => {
    pool.push(cleanFragment(fragment, 80));
  });

  pool.push(`Неверный вариант ${index + 1}`);
  pool.push(`Ошибочный ответ ${index + 1}`);
  pool.push(`Дополнительный термин ${index + 1}`);

  const seen = new Set();
  const uniquePool = [];

  pool.forEach((item) => {
    const key = normalizeText(item);
    if (!seen.has(key) && key && key !== normalizeText(correctAnswer)) {
      seen.add(key);
      uniquePool.push(item);
    }
  });

  shuffleInPlace(uniquePool);
  return uniquePool;
}

function renderOpenQuestions(questionItems, mountNode, formIdPrefix = "open", withTimer = false) {
  mountNode.innerHTML = "";

  if (withTimer && currentSessionPayload) {
    const timerBox = document.createElement("div");
    timerBox.className = "timer-box";
    timerBox.innerHTML = `
      <h3>Таймер</h3>
      <div class="timer-value" id="${formIdPrefix}_timerValue">00:00</div>
    `;
    mountNode.appendChild(timerBox);
    startOpenQuestionsTimer(currentSessionPayload.openTimerMinutes * 60, `${formIdPrefix}_timerValue`);
  }

  const form = document.createElement("form");
  form.id = `${formIdPrefix}QuestionsForm`;

  questionItems.forEach((item, index) => {
    const block = document.createElement("div");
    block.className = "question-item";

    block.innerHTML = `
      <div class="question-title">${index + 1}. ${escapeHtml(item.question)}</div>
      <textarea class="open-answer" name="${formIdPrefix}_${index}" placeholder="Введите ваш ответ..."></textarea>
      <div class="answer-feedback" id="${formIdPrefix}_feedback_${index}"></div>
    `;

    form.appendChild(block);
  });

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "btn btn-primary";
  submitBtn.textContent = "Проверить ответы";

  form.appendChild(submitBtn);

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    checkOpenQuestions(questionItems, form, formIdPrefix);
  });

  mountNode.appendChild(form);
}

function startOpenQuestionsTimer(seconds, timerElementId) {
  if (openQuestionTimerInterval) {
    clearInterval(openQuestionTimerInterval);
  }

  openQuestionTimeLeft = seconds;
  updateTimerDisplay(timerElementId);

  openQuestionTimerInterval = setInterval(() => {
    openQuestionTimeLeft--;
    updateTimerDisplay(timerElementId);

    if (openQuestionTimeLeft <= 0) {
      clearInterval(openQuestionTimerInterval);
      openQuestionTimerInterval = null;
      const form = document.querySelector(`#${timerElementId.replace("_timerValue", "")}QuestionsForm`);
      if (form) {
        const submitEvent = new Event("submit", { cancelable: true, bubbles: true });
        form.dispatchEvent(submitEvent);
      }
    }
  }, 1000);
}

function updateTimerDisplay(timerElementId) {
  const timerElement = document.getElementById(timerElementId);
  if (!timerElement) return;

  const minutes = Math.floor(openQuestionTimeLeft / 60);
  const seconds = openQuestionTimeLeft % 60;
  timerElement.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function checkOpenQuestions(questionItems, form, prefix) {
  let score = 0;
  const answersForSave = [];

  questionItems.forEach((item, index) => {
    const input = form.querySelector(`[name="${prefix}_${index}"]`);
    const feedback = form.querySelector(`#${prefix}_feedback_${index}`);
    const userAnswer = normalizeText(input.value);
    const correctAnswer = normalizeText(item.correctAnswer);
    const isCorrect = userAnswer && isAnswerCorrect(userAnswer, correctAnswer);

    answersForSave.push({
      question: item.question,
      userAnswer: input.value,
      correctAnswer: item.correctAnswer,
      isCorrect: !!isCorrect
    });

    if (isCorrect) {
      score++;
      input.classList.remove("wrong-answer");
      input.classList.add("correct-answer");
      feedback.innerHTML = `<span class="success-text">Верно</span>`;
    } else {
      input.classList.remove("correct-answer");
      input.classList.add("wrong-answer");
      feedback.innerHTML = `
        <span class="error-text">Неверно.</span>
        <div class="correct-hint">Правильный ответ: ${escapeHtml(item.correctAnswer)}</div>
      `;
    }
  });

  if (currentSessionPayload) {
    currentSessionPayload.openResults = answersForSave;
    persistCurrentPayload();
  }

  const oldScore = form.querySelector(".score-box");
  if (oldScore) oldScore.remove();

  const scoreBox = document.createElement("div");
  scoreBox.className = "score-box";
  scoreBox.textContent = `Ваш результат: ${score} из ${questionItems.length}`;

  form.appendChild(scoreBox);
}

function isAnswerCorrect(userAnswer, correctAnswer) {
  if (userAnswer === correctAnswer) return true;
  if (correctAnswer.includes(userAnswer) && userAnswer.length > 4) return true;
  if (userAnswer.includes(correctAnswer) && correctAnswer.length > 4) return true;
  return false;
}

function normalizeText(text) {
  return String(text)
    .toLowerCase()
    .replace(/[.,!?;:()"«»]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function renderTest(testItems, mountNode) {
  const form = document.createElement("form");
  form.id = "testForm";

  testItems.forEach((item, index) => {
    const block = document.createElement("div");
    block.className = "question-item";

    let optionsHtml = "";
    item.options.forEach((option) => {
      optionsHtml += `
        <label class="option">
          <input type="radio" name="question_${index}" value="${escapeHtml(option)}">
          <span>${escapeHtml(option)}</span>
        </label>
      `;
    });

    block.innerHTML = `
      <div class="question-title">${index + 1}. ${escapeHtml(item.question)}</div>
      ${optionsHtml}
    `;

    form.appendChild(block);
  });

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "btn btn-primary";
  submitBtn.textContent = "Проверить результат";

  form.appendChild(submitBtn);

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    checkTestAnswers(testItems, form);
  });

  mountNode.appendChild(form);
}

function checkTestAnswers(questions, form) {
  let score = 0;
  const answersForSave = [];

  questions.forEach((item, index) => {
    const selected = form.querySelector(`input[name="question_${index}"]:checked`);
    const options = form.querySelectorAll(`input[name="question_${index}"]`);

    options.forEach((input) => {
      const label = input.parentElement;
      label.classList.remove("correct", "wrong");

      if (normalizeText(input.value) === normalizeText(item.correctAnswer)) {
        label.classList.add("correct");
      }
    });

    const selectedValue = selected ? selected.value : "";
    const isCorrect = selected && normalizeText(selected.value) === normalizeText(item.correctAnswer);

    answersForSave.push({
      question: item.question,
      userAnswer: selectedValue,
      correctAnswer: item.correctAnswer,
      isCorrect: !!isCorrect
    });

    if (isCorrect) {
      score++;
    } else if (selected) {
      selected.parentElement.classList.add("wrong");
    }
  });

  const percent = questions.length ? Math.round((score / questions.length) * 100) : 0;

  if (currentSessionPayload) {
    currentSessionPayload.testResults = {
      score,
      total: questions.length,
      percent,
      answers: answersForSave
    };
    persistCurrentPayload();
  }

  const oldScore = form.querySelector(".score-box");
  if (oldScore) oldScore.remove();

  const oldPercent = form.querySelector(".percent-badge");
  if (oldPercent) oldPercent.remove();

  const scoreBox = document.createElement("div");
  scoreBox.className = "score-box";
  scoreBox.textContent = `Ваш результат: ${score} из ${questions.length}`;

  const percentBox = document.createElement("div");
  percentBox.className = "percent-badge";
  percentBox.textContent = `Процент правильных ответов: ${percent}%`;

  form.appendChild(scoreBox);
  form.appendChild(percentBox);
}

function loadSessionPage() {
  if (!sessionContainer) return;

  const payload = getPayloadFromUrlOrStorage();

  if (!payload) {
    sessionContainer.innerHTML =
      `<p class="empty-text">Данные не найдены. Сначала создайте генерацию на главной странице.</p>`;
    return;
  }

  currentSessionPayload = payload;

  if (sessionTitle) sessionTitle.textContent = "Результат генерации";
  if (sessionInfo) sessionInfo.textContent = `Тема: ${payload.topic}`;
  if (sessionModeInfo) sessionModeInfo.textContent = `Режим: ${getModeLabel(payload.mode)}`;

  fillLinks(payload);
  renderSessionContent(payload);
  initEditorActions();
  initPdfActions();
}

function renderSessionContent(payload) {
  sessionContainer.innerHTML = "";

  const editorBox = document.createElement("div");
  editorBox.className = "editor-box hidden";
  editorBox.id = "editorBox";
  sessionContainer.appendChild(editorBox);
  renderEditor(payload, editorBox);

  if (payload.mode === "questions") {
    const banner = document.createElement("div");
    banner.className = "info-banner";
    banner.textContent = "Открыт режим обычных вопросов.";
    sessionContainer.appendChild(banner);

    const block = document.createElement("div");
    block.className = "section-block";
    block.innerHTML = `<h3>Обычные вопросы</h3>`;
    sessionContainer.appendChild(block);

    const mount = document.createElement("div");
    mount.id = "openQuestionsMount";
    sessionContainer.appendChild(mount);
    renderOpenQuestions(payload.questions, mount, "session_open", true);
    return;
  }

  if (payload.mode === "test") {
    const banner = document.createElement("div");
    banner.className = "info-banner";
    banner.textContent = "Открыт режим теста со случайными вопросами.";
    sessionContainer.appendChild(banner);

    const block = document.createElement("div");
    block.className = "section-block";
    block.innerHTML = `<h3>Тест</h3>`;
    sessionContainer.appendChild(block);

    const mount = document.createElement("div");
    mount.id = "testMount";
    sessionContainer.appendChild(mount);
    renderTest(payload.test, mount);
    return;
  }

  if (payload.mode === "mixed") {
    const banner = document.createElement("div");
    banner.className = "info-banner";
    banner.textContent = "Открыт смешанный режим: обычные вопросы и тест вместе.";
    sessionContainer.appendChild(banner);

    const openBlock = document.createElement("div");
    openBlock.className = "section-block";
    openBlock.innerHTML = `<h3>Обычные вопросы</h3>`;
    sessionContainer.appendChild(openBlock);

    const openMount = document.createElement("div");
    openMount.id = "mixedOpenMount";
    sessionContainer.appendChild(openMount);
    renderOpenQuestions(payload.questions, openMount, "session_mixed", true);

    const separator = document.createElement("div");
    separator.className = "mixed-separator";
    separator.textContent = "Тест";
    sessionContainer.appendChild(separator);

    const testMount = document.createElement("div");
    testMount.id = "mixedTestMount";
    sessionContainer.appendChild(testMount);
    renderTest(payload.test, testMount);
  }
}

function renderEditor(payload, editorBox) {
  let html = `
    <h3>Редактор</h3>

    <div class="section-block">
      <h3>Обычные вопросы</h3>
      <div class="editor-actions">
        <button type="button" class="btn btn-primary btn-small" id="addOpenQuestionBtn">Добавить вопрос</button>
      </div>
  `;

  payload.questions.forEach((item, index) => {
    html += `
      <div class="editor-item">
        <h4>Вопрос ${index + 1}</h4>
        <div class="mini-field">
          <label>Текст вопроса</label>
          <textarea data-edit-type="open-question" data-index="${index}">${escapeHtml(item.question)}</textarea>
        </div>
        <div class="mini-field">
          <label>Правильный ответ</label>
          <textarea data-edit-type="open-answer" data-index="${index}">${escapeHtml(item.correctAnswer)}</textarea>
        </div>
        <button type="button" class="btn btn-danger btn-small" data-delete-open="${index}">Удалить вопрос</button>
      </div>
    `;
  });

  html += `</div>`;

  html += `
    <div class="section-block">
      <h3>Тест</h3>
      <div class="editor-actions">
        <button type="button" class="btn btn-primary btn-small" id="addTestQuestionBtn">Добавить вопрос</button>
      </div>
  `;

  payload.test.forEach((item, index) => {
    html += `
      <div class="editor-item">
        <h4>Тестовый вопрос ${index + 1}</h4>
        <div class="mini-field">
          <label>Текст вопроса</label>
          <textarea data-edit-type="test-question" data-index="${index}">${escapeHtml(item.question)}</textarea>
        </div>
    `;

    item.options.forEach((option, optionIndex) => {
      const isCorrect = normalizeText(option) === normalizeText(item.correctAnswer);
      html += `
        <div class="option-edit">
          <input
            type="text"
            value="${escapeHtml(option)}"
            data-edit-type="test-option"
            data-index="${index}"
            data-option-index="${optionIndex}"
          />
          <span class="correct-mark">${isCorrect ? "Правильный" : ""}</span>
          <button type="button" class="btn btn-danger btn-small" data-delete-option="${index}:${optionIndex}">Удалить</button>
        </div>
      `;
    });

    html += `
        <div class="editor-actions">
          <button type="button" class="btn btn-primary btn-small" data-add-option="${index}">Добавить вариант ответа</button>
        </div>
        <div class="mini-field">
          <label>Правильный ответ</label>
          <input
            type="text"
            value="${escapeHtml(item.correctAnswer)}"
            data-edit-type="test-correct"
            data-index="${index}"
          />
        </div>
        <button type="button" class="btn btn-danger btn-small" data-delete-test="${index}">Удалить вопрос</button>
      </div>
    `;
  });

  html += `</div>`;
  editorBox.innerHTML = html;
}

function initEditorActions() {
  if (toggleEditBtn) {
    toggleEditBtn.onclick = function () {
      editMode = !editMode;
      const editorBox = document.getElementById("editorBox");
      if (!editorBox) return;
      editorBox.classList.toggle("hidden", !editMode);
    };
  }

  if (saveEditsBtn) {
    saveEditsBtn.onclick = function () {
      if (!currentSessionPayload) return;

      document.querySelectorAll('[data-edit-type="open-question"]').forEach((el) => {
        const index = Number(el.dataset.index);
        currentSessionPayload.questions[index].question = el.value.trim();
      });

      document.querySelectorAll('[data-edit-type="open-answer"]').forEach((el) => {
        const index = Number(el.dataset.index);
        currentSessionPayload.questions[index].correctAnswer = el.value.trim();
      });

      document.querySelectorAll('[data-edit-type="test-question"]').forEach((el) => {
        const index = Number(el.dataset.index);
        currentSessionPayload.test[index].question = el.value.trim();
      });

      document.querySelectorAll('[data-edit-type="test-option"]').forEach((el) => {
        const index = Number(el.dataset.index);
        const optionIndex = Number(el.dataset.optionIndex);
        currentSessionPayload.test[index].options[optionIndex] = el.value.trim();
      });

      document.querySelectorAll('[data-edit-type="test-correct"]').forEach((el) => {
        const index = Number(el.dataset.index);
        currentSessionPayload.test[index].correctAnswer = el.value.trim();
      });

      persistCurrentPayload();
      renderSessionContent(currentSessionPayload);
      initEditorActions();
      initPdfActions();
      alert("Изменения сохранены");
    };
  }

  document.getElementById("addOpenQuestionBtn")?.addEventListener("click", () => {
    if (!currentSessionPayload) return;
    currentSessionPayload.questions.push({
      question: "Новый вопрос",
      correctAnswer: "Новый ответ"
    });
    persistCurrentPayload();
    renderSessionContent(currentSessionPayload);
    initEditorActions();
    initPdfActions();
  });

  document.getElementById("addTestQuestionBtn")?.addEventListener("click", () => {
    if (!currentSessionPayload) return;
    currentSessionPayload.test.push({
      question: "Новый тестовый вопрос",
      correctAnswer: "Правильный ответ",
      options: ["Правильный ответ", "Вариант 2", "Вариант 3", "Вариант 4"]
    });
    persistCurrentPayload();
    renderSessionContent(currentSessionPayload);
    initEditorActions();
    initPdfActions();
  });

  document.querySelectorAll("[data-delete-open]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = Number(btn.dataset.deleteOpen);
      currentSessionPayload.questions.splice(index, 1);
      persistCurrentPayload();
      renderSessionContent(currentSessionPayload);
      initEditorActions();
      initPdfActions();
    });
  });

  document.querySelectorAll("[data-delete-test]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = Number(btn.dataset.deleteTest);
      currentSessionPayload.test.splice(index, 1);
      persistCurrentPayload();
      renderSessionContent(currentSessionPayload);
      initEditorActions();
      initPdfActions();
    });
  });

  document.querySelectorAll("[data-add-option]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = Number(btn.dataset.addOption);
      currentSessionPayload.test[index].options.push("Новый вариант");
      persistCurrentPayload();
      renderSessionContent(currentSessionPayload);
      initEditorActions();
      initPdfActions();
    });
  });

  document.querySelectorAll("[data-delete-option]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const [qIndex, optionIndex] = btn.dataset.deleteOption.split(":").map(Number);
      if (currentSessionPayload.test[qIndex].options.length > 1) {
        currentSessionPayload.test[qIndex].options.splice(optionIndex, 1);
        persistCurrentPayload();
        renderSessionContent(currentSessionPayload);
        initEditorActions();
        initPdfActions();
      }
    });
  });
}

function getModeLabel(mode) {
  if (mode === "questions") return "Только вопросы";
  if (mode === "test") return "Тест";
  if (mode === "mixed") return "Смешанный";
  return "Неизвестно";
}

function getPayloadFromUrlOrStorage() {
  const url = new URL(window.location.href);
  const id = url.searchParams.get("id");

  if (id) {
    const saved = localStorage.getItem(`masterTest_${id}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return null;
      }
    }
  }

  const hash = window.location.hash;
  if (hash.startsWith("#data=")) {
    const encoded = hash.replace("#data=", "");
    try {
      return decodePayload(encoded);
    } catch {
      return null;
    }
  }

  const lastId = localStorage.getItem("masterTest_last");
  if (lastId) {
    const saved = localStorage.getItem(`masterTest_${lastId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return null;
      }
    }
  }

  return null;
}

function fillLinks(payload) {
  const currentBase = window.location.origin + window.location.pathname.replace(/[^/]+$/, "");
  const shortLink = `${currentBase}session.html?id=${encodeURIComponent(payload.id)}`;
  const shareLink = `${currentBase}session.html#data=${encodeURIComponent(encodePayload(payload))}`;

  if (localLinkInput) localLinkInput.value = shortLink;
  if (shareLinkInput) shareLinkInput.value = shareLink;

  if (copyLocalLinkBtn) {
    copyLocalLinkBtn.onclick = () => copyToClipboard(shortLink);
  }

  if (copyShareLinkBtn) {
    copyShareLinkBtn.onclick = () => copyToClipboard(shareLink);
  }
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    alert("Ссылка скопирована");
  } catch {
    alert("Не удалось скопировать ссылку");
  }
}

function encodePayload(payload) {
  const json = JSON.stringify(payload);
  return btoa(unescape(encodeURIComponent(json)));
}

function decodePayload(encoded) {
  const json = decodeURIComponent(escape(atob(encoded)));
  return JSON.parse(json);
}

function generateId() {
  return "t" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function shuffleArray(array) {
  const copy = [...array];
  shuffleInPlace(copy);
  return copy;
}

function shuffleInPlace(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

function persistCurrentPayload() {
  if (!currentSessionPayload) return;
  localStorage.setItem(`masterTest_${currentSessionPayload.id}`, JSON.stringify(currentSessionPayload));
  localStorage.setItem("masterTest_last", currentSessionPayload.id);
  fillLinks(currentSessionPayload);
}

function initPdfActions() {
  if (downloadTestPdfBtn) {
    downloadTestPdfBtn.onclick = () => downloadTestPdf();
  }

  if (downloadResultsPdfBtn) {
    downloadResultsPdfBtn.onclick = () => downloadResultsPdf();
  }
}

function addPdfLine(doc, state, text, gap = 8) {
  const lines = doc.splitTextToSize(text, 180);
  doc.text(lines, 15, state.y);
  state.y += lines.length * 7 + gap;
  if (state.y > 270) {
    doc.addPage();
    state.y = 15;
  }
}

function downloadTestPdf() {
  if (!currentSessionPayload || !window.jspdf) return;

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  const state = { y: 15 };

  addPdfLine(doc, state, "Мастер тестов");
  addPdfLine(doc, state, `Тема: ${currentSessionPayload.topic}`);
  addPdfLine(doc, state, `Режим: ${getModeLabel(currentSessionPayload.mode)}`);

  if (currentSessionPayload.mode === "questions" || currentSessionPayload.mode === "mixed") {
    addPdfLine(doc, state, "Обычные вопросы:");
    currentSessionPayload.questions.forEach((item, index) => {
      addPdfLine(doc, state, `${index + 1}. ${item.question}`);
    });
  }

  if (currentSessionPayload.mode === "test" || currentSessionPayload.mode === "mixed") {
    addPdfLine(doc, state, "Тест:");
    currentSessionPayload.test.forEach((item, index) => {
      addPdfLine(doc, state, `${index + 1}. ${item.question}`);
      item.options.forEach((option, optionIndex) => {
        addPdfLine(doc, state, `   ${optionIndex + 1}) ${option}`, 4);
      });
    });
  }

  doc.save("master-test-test.pdf");
}

function downloadResultsPdf() {
  if (!currentSessionPayload || !window.jspdf) return;

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  const state = { y: 15 };

  addPdfLine(doc, state, "Мастер тестов — ответы и результаты");
  addPdfLine(doc, state, `Тема: ${currentSessionPayload.topic}`);
  addPdfLine(doc, state, `Режим: ${getModeLabel(currentSessionPayload.mode)}`);

  if (currentSessionPayload.openResults && currentSessionPayload.openResults.length > 0) {
    addPdfLine(doc, state, "Обычные вопросы:");
    currentSessionPayload.openResults.forEach((item, index) => {
      addPdfLine(doc, state, `${index + 1}. ${item.question}`);
      addPdfLine(doc, state, `Ответ пользователя: ${item.userAnswer || "—"}`, 4);
      addPdfLine(doc, state, `Правильный ответ: ${item.correctAnswer}`, 4);
      addPdfLine(doc, state, `Результат: ${item.isCorrect ? "Верно" : "Неверно"}`);
    });
  } else if (currentSessionPayload.mode === "questions" || currentSessionPayload.mode === "mixed") {
    addPdfLine(doc, state, "Обычные вопросы пока не были проверены.");
  }

  if (currentSessionPayload.testResults && currentSessionPayload.testResults.answers) {
    addPdfLine(doc, state, "Тест:");
    addPdfLine(doc, state, `Баллы: ${currentSessionPayload.testResults.score} из ${currentSessionPayload.testResults.total}`);
    addPdfLine(doc, state, `Процент: ${currentSessionPayload.testResults.percent}%`);

    currentSessionPayload.testResults.answers.forEach((item, index) => {
      addPdfLine(doc, state, `${index + 1}. ${item.question}`);
      addPdfLine(doc, state, `Ответ пользователя: ${item.userAnswer || "—"}`, 4);
      addPdfLine(doc, state, `Правильный ответ: ${item.correctAnswer}`, 4);
      addPdfLine(doc, state, `Результат: ${item.isCorrect ? "Верно" : "Неверно"}`);
    });
  } else if (currentSessionPayload.mode === "test" || currentSessionPayload.mode === "mixed") {
    addPdfLine(doc, state, "Тест пока не был проверен.");
  }

  doc.save("master-test-results.pdf");
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

updatePreview();
loadSessionPage();