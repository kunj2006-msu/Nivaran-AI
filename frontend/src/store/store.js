/**
 * ShopNest E-Commerce Storefront Engine
 * Handles catalog rendering, product details, slide-in cart, checkout form validation,
 * and order submissions wired to the FastAPI backend API.
 */

let apiBaseUrl = '';
let storeProducts = [];
let activeProduct = null;
let detailQuantity = 1;
let cartItems = []; // Array of { product, quantity }

// Image fallback map for products without external images
const PRODUCT_IMAGES = {
  1: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=60',
  2: 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop&q=60',
  3: 'https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=500&auto=format&fit=crop&q=60',
  4: 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=500&auto=format&fit=crop&q=60',
  5: 'https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=500&auto=format&fit=crop&q=60'
};

// 1. API Base Detection
async function detectApiBase() {
  const candidates = [
    window.location.origin,
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:3000',
    'http://127.0.0.1:3000'
  ];

  for (const base of candidates) {
    if (!base || base.startsWith('file://')) continue;
    try {
      const res = await fetch(`${base}/health`, { method: 'GET' });
      if (res.ok) {
        apiBaseUrl = base;
        console.log(`✅ Storefront connected to Nivaran AI API base: ${apiBaseUrl}`);
        return apiBaseUrl;
      }
    } catch (e) {
      // Try next
    }
  }

  apiBaseUrl = 'http://localhost:8000';
  return apiBaseUrl;
}

// 2. Fetch Products
async function loadProducts() {
  await detectApiBase();
  const grid = document.getElementById('products-grid');

  try {
    const response = await fetch(`${apiBaseUrl}/api/store/products`);
    if (!response.ok) throw new Error('API request failed');

    storeProducts = await response.json();
    renderProductsGrid(storeProducts);
  } catch (err) {
    console.warn('⚠️ Unable to connect to backend store endpoint, displaying default catalog:', err);
    storeProducts = [
      { id: 1, name: 'Aura Wireless Headphones', description: 'Active noise cancelling wireless headphones with 40h battery life and spatial audio.', price: 129.99, image_url: PRODUCT_IMAGES[1], stock: 15, status: 'active' },
      { id: 2, name: 'Pulse Fitness Smartwatch', description: 'Waterproof fitness smartwatch with AMOLED display, heart rate tracking, and GPS.', price: 179.99, image_url: PRODUCT_IMAGES[2], stock: 8, status: 'active' },
      { id: 3, name: 'SonicBoom Bluetooth Speaker', description: 'Compact waterproof Bluetooth speaker delivering 360-degree immersive bass sound.', price: 69.99, image_url: PRODUCT_IMAGES[3], stock: 20, status: 'active' },
      { id: 4, name: 'ZenErgo Mechanical Keyboard', description: 'RGB tactile wireless mechanical keyboard with hot-swappable switches and wrist rest.', price: 119.99, image_url: PRODUCT_IMAGES[4], stock: 5, status: 'active' },
      { id: 5, name: 'Clarion HD Ergonomic Earbuds', description: 'True wireless in-ear earbuds with dual mic noise suppression and instant pairing.', price: 49.99, image_url: PRODUCT_IMAGES[5], stock: 0, status: 'active' }
    ];
    renderProductsGrid(storeProducts);
  }
}

// 3. Render Product Cards Grid
function renderProductsGrid(products) {
  const grid = document.getElementById('products-grid');
  if (!grid) return;

  if (products.length === 0) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-muted);">No products available in store right now.</div>`;
    return;
  }

  grid.innerHTML = products.map(p => {
    const imgUrl = p.image_url || PRODUCT_IMAGES[p.id] || 'https://via.placeholder.com/300?text=Product';
    let stockBadgeClass = 'in-stock';
    let stockBadgeText = `In Stock: ${p.stock}`;

    if (p.stock === 0) {
      stockBadgeClass = 'out-of-stock';
      stockBadgeText = 'Out of Stock';
    } else if (p.stock <= 5) {
      stockBadgeClass = 'low-stock';
      stockBadgeText = `Only ${p.stock} left`;
    }

    return `
      <div class="product-card" onclick="openProductDetail(${p.id})">
        <div class="product-image-wrap">
          <img src="${imgUrl}" alt="${p.name}" class="product-img" loading="lazy" />
          <span class="stock-badge ${stockBadgeClass}">${stockBadgeText}</span>
        </div>
        <div class="product-info">
          <h3 class="product-name">${p.name}</h3>
          <p class="product-desc-snippet">${p.description || ''}</p>
          <div class="product-card-footer">
            <span class="product-price">$${parseFloat(p.price).toFixed(2)}</span>
            <button class="btn-card-action" onclick="event.stopPropagation(); openProductDetail(${p.id})">
              ${p.stock > 0 ? 'View Details' : 'Out of Stock'}
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// 4. Product Detail Modal
async function openProductDetail(productId) {
  activeProduct = storeProducts.find(p => p.id === productId);
  
  if (!activeProduct) {
    try {
      const res = await fetch(`${apiBaseUrl}/api/store/products/${productId}`);
      if (res.ok) activeProduct = await res.json();
    } catch (e) {
      console.error(e);
    }
  }

  if (!activeProduct) return;

  detailQuantity = activeProduct.stock > 0 ? 1 : 0;
  
  const imgUrl = activeProduct.image_url || PRODUCT_IMAGES[activeProduct.id] || 'https://via.placeholder.com/400';
  document.getElementById('detail-img').src = imgUrl;
  document.getElementById('detail-name').innerText = activeProduct.name;
  document.getElementById('detail-price').innerText = `$${parseFloat(activeProduct.price).toFixed(2)}`;
  document.getElementById('detail-desc').innerText = activeProduct.description || 'No description available.';
  
  const stockBadgeEl = document.getElementById('detail-stock-badge');
  if (activeProduct.stock > 0) {
    stockBadgeEl.className = 'stock-badge in-stock';
    stockBadgeEl.innerText = `In Stock (${activeProduct.stock} available)`;
  } else {
    stockBadgeEl.className = 'stock-badge out-of-stock';
    stockBadgeEl.innerText = 'Out of Stock';
  }

  updateDetailQuantityDisplay();

  const addBtn = document.getElementById('detail-add-btn');
  if (activeProduct.stock > 0) {
    addBtn.disabled = false;
    addBtn.innerText = 'Add to Cart';
  } else {
    addBtn.disabled = true;
    addBtn.innerText = 'Out of Stock';
  }

  openOverlay('modal-detail');
}

function updateDetailQuantityDisplay() {
  document.getElementById('detail-qty-val').innerText = detailQuantity;
  document.getElementById('btn-qty-minus').disabled = detailQuantity <= 1;
  document.getElementById('btn-qty-plus').disabled = !activeProduct || detailQuantity >= activeProduct.stock;
}

function stepDetailQuantity(delta) {
  if (!activeProduct) return;
  const newQty = detailQuantity + delta;
  if (newQty >= 1 && newQty <= activeProduct.stock) {
    detailQuantity = newQty;
    updateDetailQuantityDisplay();
  }
}

function addDetailItemToCart() {
  if (!activeProduct || activeProduct.stock <= 0) return;
  addToCart(activeProduct, detailQuantity);
  closeOverlay('modal-detail');
  openCartDrawer();
}

// 5. Cart Management
function addToCart(product, quantity) {
  const existing = cartItems.find(item => item.product.id === product.id);
  if (existing) {
    const totalQty = existing.quantity + quantity;
    existing.quantity = Math.min(totalQty, product.stock);
  } else {
    cartItems.push({ product, quantity: Math.min(quantity, product.stock) });
  }

  updateCartUI();
}

function updateCartItemQty(productId, delta) {
  const item = cartItems.find(i => i.product.id === productId);
  if (!item) return;

  const newQty = item.quantity + delta;
  if (newQty <= 0) {
    removeFromCart(productId);
  } else if (newQty <= item.product.stock) {
    item.quantity = newQty;
    updateCartUI();
  }
}

function removeFromCart(productId) {
  cartItems = cartItems.filter(i => i.product.id !== productId);
  updateCartUI();
}

function calculateSubtotal() {
  return cartItems.reduce((acc, item) => acc + (item.product.price * item.quantity), 0);
}

function updateCartUI() {
  const totalCount = cartItems.reduce((acc, item) => acc + item.quantity, 0);
  
  // Badges
  const headerBadge = document.getElementById('header-cart-badge');
  const navBadge = document.getElementById('nav-cart-badge');

  if (headerBadge) headerBadge.innerText = totalCount;
  if (navBadge) navBadge.innerText = totalCount;

  // Drawer Content
  const bodyEl = document.getElementById('cart-drawer-body');
  const footerEl = document.getElementById('cart-drawer-footer');
  const checkoutBtn = document.getElementById('cart-checkout-btn');

  if (cartItems.length === 0) {
    bodyEl.innerHTML = `
      <div class="cart-empty-state">
        <div class="empty-icon">🛒</div>
        <h3>Your Cart is Empty</h3>
        <p style="font-size: 0.9rem;">Browse our store items and add products to your cart!</p>
      </div>
    `;
    if (footerEl) footerEl.style.display = 'none';
  } else {
    if (footerEl) footerEl.style.display = 'block';

    bodyEl.innerHTML = cartItems.map(item => {
      const p = item.product;
      const imgUrl = p.image_url || PRODUCT_IMAGES[p.id] || 'https://via.placeholder.com/100';
      return `
        <div class="cart-item">
          <img src="${imgUrl}" alt="${p.name}" class="cart-item-img" />
          <div class="cart-item-details">
            <h4 class="cart-item-name">${p.name}</h4>
            <div class="cart-item-price">$${(p.price * item.quantity).toFixed(2)}</div>
            <div class="cart-controls">
              <button class="stepper-btn" onclick="updateCartItemQty(${p.id}, -1)">-</button>
              <span class="stepper-val">${item.quantity}</span>
              <button class="stepper-btn" onclick="updateCartItemQty(${p.id}, 1)" ${item.quantity >= p.stock ? 'disabled' : ''}>+</button>
            </div>
          </div>
          <button class="btn-remove-item" onclick="removeFromCart(${p.id})" title="Remove item">✕</button>
        </div>
      `;
    }).join('');

    const subtotal = calculateSubtotal();
    document.getElementById('cart-subtotal').innerText = `$${subtotal.toFixed(2)}`;
  }
}

// 6. Overlays & Modal Controls
function openOverlay(type) {
  const backdrop = document.getElementById('overlay-backdrop');
  backdrop.classList.add('active');

  if (type === 'cart') {
    backdrop.classList.add('cart-active');
  } else {
    backdrop.classList.add('modal-active');
    document.querySelectorAll('.modal-box').forEach(m => m.classList.remove('active'));
    const modal = document.getElementById(type);
    if (modal) modal.classList.add('active');
  }
}

function closeOverlay(type) {
  const backdrop = document.getElementById('overlay-backdrop');

  if (type === 'cart') {
    backdrop.classList.remove('cart-active');
  } else if (type) {
    const modal = document.getElementById(type);
    if (modal) modal.classList.remove('active');
  }

  // If no remaining active drawers/modals, hide backdrop
  const hasActiveModal = document.querySelector('.modal-box.active');
  const isCartActive = backdrop.classList.contains('cart-active');
  
  if (!hasActiveModal && !isCartActive) {
    backdrop.classList.remove('active', 'modal-active');
  }
}

function closeAllOverlays() {
  const backdrop = document.getElementById('overlay-backdrop');
  backdrop.className = 'overlay-backdrop';
  document.querySelectorAll('.modal-box').forEach(m => m.classList.remove('active'));
  closeVoiceAssistant();
}

function openCartDrawer() {
  openOverlay('cart');
}

function closeCartDrawer() {
  closeOverlay('cart');
}

function openCheckoutModal() {
  if (cartItems.length === 0) return;
  closeCartDrawer();

  // Reset form inputs & validation messages
  ['cust-name', 'cust-address', 'cust-email'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.value = '';
      el.classList.remove('is-invalid');
    }
  });

  const checkoutSubtotal = calculateSubtotal();
  document.getElementById('checkout-total-display').innerText = `$${checkoutSubtotal.toFixed(2)}`;

  openOverlay('modal-checkout');
}

// 7. Form Validation
function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// 8. Submit Checkout Order
async function submitCheckoutOrder() {
  const nameEl = document.getElementById('cust-name');
  const addressEl = document.getElementById('cust-address');
  const emailEl = document.getElementById('cust-email');

  const name = nameEl.value.trim();
  const address = addressEl.value.trim();
  const email = emailEl.value.trim();

  let isValid = true;

  if (!name) {
    nameEl.classList.add('is-invalid');
    isValid = false;
  } else {
    nameEl.classList.remove('is-invalid');
  }

  if (!address) {
    addressEl.classList.add('is-invalid');
    isValid = false;
  } else {
    addressEl.classList.remove('is-invalid');
  }

  if (!email || !validateEmail(email)) {
    emailEl.classList.add('is-invalid');
    isValid = false;
  } else {
    emailEl.classList.remove('is-invalid');
  }

  if (!isValid) return;

  const orderPayload = {
    customer: { name, email, address, phone: '' },
    items: cartItems.map(item => ({
      product_id: item.product.id,
      quantity: item.quantity
    }))
  };

  const submitBtn = document.getElementById('btn-submit-order');
  const originalText = submitBtn.innerHTML;
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="spinner"></span> Processing Order...`;

  try {
    const response = await fetch(`${apiBaseUrl}/api/store/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(orderPayload)
    });

    const data = await response.json();

    if (!response.ok) {
      let errorMsg = 'Order submission failed.';
      if (typeof data.detail === 'string') {
        errorMsg = data.detail;
      } else if (Array.isArray(data.detail)) {
        errorMsg = data.detail.map(d => `${d.loc ? d.loc.slice(1).join('.') : 'field'}: ${d.msg}`).join(', ');
      }
      throw new Error(errorMsg);
    }

    // Success
    closeOverlay('modal-checkout');
    showOrderSuccessConfirmation(data);

    // Save customer email for Voice Assistant personalization
    if (orderPayload.customer && orderPayload.customer.email) {
      localStorage.setItem('shopnest_customer_email', orderPayload.customer.email);
    }

    // Clear cart & refresh inventory stock levels
    cartItems = [];
    updateCartUI();
    loadProducts();

  } catch (err) {
    alert(`Order placement error: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = originalText;
  }
}

// 9. Show Success Modal
function showOrderSuccessConfirmation(orderData) {
  document.getElementById('confirm-order-id').innerText = orderData.order_id;
  document.getElementById('confirm-customer-name').innerText = orderData.customer.name;
  document.getElementById('confirm-email').innerText = orderData.customer.email;
  document.getElementById('confirm-total').innerText = `$${parseFloat(orderData.total).toFixed(2)}`;

  openOverlay('modal-success');
}

// ==========================================================================
// 10. Nivaran AI Interactive Voice Assistant Engine
// ==========================================================================

let isVoiceAssistantOpen = false;
let isRecording = false;
let isAudioOutputEnabled = true;
let mediaRecorder = null;
let audioChunks = [];
let speechRecognition = null;
let currentPlayingAudio = null;
let messageCounter = 0;

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatBotMarkdown(text) {
  if (!text) return '';
  let formatted = escapeHtml(text);
  // Bold **text** -> <strong>text</strong>
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Italic *text* or _text_ -> <em>text</em>
  formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
  // Code `text` -> <code>text</code>
  formatted = formatted.replace(/`(.*?)`/g, '<code style="background:rgba(0,0,0,0.06);padding:2px 5px;border-radius:4px;font-size:0.85em;">$1</code>');
  // Bullet lists
  formatted = formatted.replace(/^\s*•\s*(.*)$/gm, '<li>$1</li>');
  formatted = formatted.replace(/^\s*-\s*(.*)$/gm, '<li>$1</li>');
  // Newlines to <br>
  formatted = formatted.replace(/\n\n/g, '<br><br>');
  formatted = formatted.replace(/\n/g, '<br>');
  return formatted;
}

function setVoiceStatus(statusText, stateClass) {
  const pill = document.getElementById('voice-status-pill');
  if (!pill) return;
  pill.innerText = statusText;
  if (stateClass === 'listening') {
    pill.style.color = '#ef4444';
    pill.innerHTML = '🔴 Listening...';
  } else if (stateClass === 'thinking') {
    pill.style.color = '#fbbf24';
    pill.innerHTML = '⚡ Thinking...';
  } else if (stateClass === 'speaking') {
    pill.style.color = '#34d399';
    pill.innerHTML = '🔊 Speaking...';
  } else {
    pill.style.color = 'rgba(255, 255, 255, 0.85)';
  }
}

function openVoiceAssistant() {
  const drawer = document.getElementById('drawer-voice');
  const backdrop = document.getElementById('overlay-backdrop');
  if (!drawer || !backdrop) return;

  isVoiceAssistantOpen = true;
  drawer.classList.add('open');
  backdrop.classList.add('active');
  setVoiceStatus('Ready to listen', 'ready');
  scrollVoiceChatToBottom();
}

function closeVoiceAssistant() {
  const drawer = document.getElementById('drawer-voice');
  const backdrop = document.getElementById('overlay-backdrop');

  if (isRecording) {
    stopVoiceRecording();
  }
  if (currentPlayingAudio) {
    currentPlayingAudio.pause();
    currentPlayingAudio = null;
  }

  isVoiceAssistantOpen = false;
  if (drawer) drawer.classList.remove('open');

  const hasActiveModal = document.querySelector('.modal-box.active');
  const isCartActive = backdrop && backdrop.classList.contains('cart-active');
  if (!hasActiveModal && !isCartActive && backdrop) {
    backdrop.classList.remove('active', 'modal-active');
  }
}

function toggleVoiceAudioOutput() {
  isAudioOutputEnabled = !isAudioOutputEnabled;
  const btn = document.getElementById('voice-speaker-btn');
  if (btn) {
    btn.innerHTML = isAudioOutputEnabled ? '🔊' : '🔇';
    btn.classList.toggle('muted', !isAudioOutputEnabled);
    btn.title = isAudioOutputEnabled ? 'Voice Response Audio: ON' : 'Voice Response Audio: MUTED';
  }
  if (!isAudioOutputEnabled && currentPlayingAudio) {
    currentPlayingAudio.pause();
  }
}

function scrollVoiceChatToBottom() {
  const feed = document.getElementById('voice-chat-feed');
  if (feed) {
    setTimeout(() => {
      feed.scrollTop = feed.scrollHeight;
    }, 50);
  }
}

function appendVoiceMessage(sender, textHtml, audioBase64 = null) {
  const feed = document.getElementById('voice-chat-feed');
  if (!feed) return null;

  messageCounter++;
  const msgId = `voice-msg-${messageCounter}`;
  const isBot = sender === 'bot';

  const msgDiv = document.createElement('div');
  msgDiv.className = `voice-msg ${isBot ? 'voice-msg-bot' : 'voice-msg-user'}`;
  msgDiv.id = msgId;

  const contentFormatted = isBot ? formatBotMarkdown(textHtml) : textHtml;

  let replayBtnHtml = '';
  if (isBot && audioBase64) {
    replayBtnHtml = `
      <button class="voice-audio-replay-btn" onclick="playVoiceAudio('${audioBase64}')" title="Replay voice audio">
        <span>🔊</span> Listen Again
      </button>
    `;
  }

  const senderTag = isBot ? '🤖 Nivaran AI' : '👤 You';

  msgDiv.innerHTML = `
    <div class="voice-msg-bubble">
      ${contentFormatted}
      ${replayBtnHtml}
    </div>
    <span class="voice-msg-tag">${senderTag}</span>
  `;

  feed.appendChild(msgDiv);
  scrollVoiceChatToBottom();
  return msgId;
}

function updateVoiceMessageContent(msgId, newHtml) {
  const msgEl = document.getElementById(msgId);
  if (!msgEl) return;
  const bubble = msgEl.querySelector('.voice-msg-bubble');
  if (bubble) {
    bubble.innerHTML = newHtml;
  }
  scrollVoiceChatToBottom();
}

function playVoiceAudio(audioBase64) {
  if (!audioBase64) return;
  if (currentPlayingAudio) {
    currentPlayingAudio.pause();
  }

  try {
    currentPlayingAudio = new Audio(audioBase64);
    setVoiceStatus('Speaking...', 'speaking');
    currentPlayingAudio.onended = () => {
      setVoiceStatus('Ready to listen', 'ready');
    };
    currentPlayingAudio.play().catch(e => {
      console.warn('Audio autoplay prevented or error:', e);
      setVoiceStatus('Ready to listen', 'ready');
    });
  } catch (e) {
    console.error('Audio playback error:', e);
  }
}

// Recording & Audio Capture Logic
async function toggleVoiceRecording() {
  if (isRecording) {
    stopVoiceRecording();
  } else {
    await startVoiceRecording();
  }
}

async function startVoiceRecording() {
  if (isRecording) return;

  const micBtn = document.getElementById('voice-mic-btn');
  const micLabel = document.getElementById('voice-mic-label');
  const transcriptBox = document.getElementById('voice-live-transcript-box');
  const transcriptText = document.getElementById('voice-transcript-text');

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];

    let mimeType = 'audio/webm';
    if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
      mimeType = 'audio/webm;codecs=opus';
    } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
      mimeType = 'audio/ogg;codecs=opus';
    } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
      mimeType = 'audio/mp4';
    }

    mediaRecorder = new MediaRecorder(stream, { mimeType });

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      const audioBlob = new Blob(audioChunks, { type: mimeType });
      if (audioBlob.size > 1000) {
        await processVoiceAudioBlob(audioBlob);
      } else {
        setVoiceStatus('Ready to listen', 'ready');
      }
    };

    mediaRecorder.start(250);
    isRecording = true;

    if (micBtn) micBtn.classList.add('recording');
    if (micLabel) micLabel.innerText = 'Listening... Tap to Stop';
    if (transcriptBox) transcriptBox.style.display = 'block';
    if (transcriptText) transcriptText.innerText = 'Listening to your voice...';
    setVoiceStatus('Listening...', 'listening');

    startLiveSpeechRecognition();

  } catch (err) {
    console.warn('Microphone permission or hardware error:', err);
    alert('Please enable microphone access in your browser to speak with Nivaran Voice AI, or type your question in the text box below.');
    setVoiceStatus('Mic error', 'error');
  }
}

function stopVoiceRecording() {
  if (!isRecording) return;
  isRecording = false;

  const micBtn = document.getElementById('voice-mic-btn');
  const micLabel = document.getElementById('voice-mic-label');

  if (micBtn) micBtn.classList.remove('recording');
  if (micLabel) micLabel.innerText = 'Processing query...';
  setVoiceStatus('Transcribing...', 'thinking');

  if (speechRecognition) {
    try { speechRecognition.stop(); } catch (e) {}
  }

  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

function startLiveSpeechRecognition() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) return;

  try {
    speechRecognition = new SpeechRec();
    speechRecognition.continuous = true;
    speechRecognition.interimResults = true;
    speechRecognition.lang = 'en-US';

    speechRecognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        interim += event.results[i][0].transcript;
      }
      const transcriptText = document.getElementById('voice-transcript-text');
      if (transcriptText && interim) {
        transcriptText.innerText = interim;
      }
    };

    speechRecognition.start();
  } catch (e) {
    // Fallback to Groq Whisper directly
  }
}

async function processVoiceAudioBlob(audioBlob) {
  const transcriptBox = document.getElementById('voice-live-transcript-box');
  const micLabel = document.getElementById('voice-mic-label');

  const tempUserMsgId = appendVoiceMessage('user', '🎤 <i>Processing voice query...</i>');
  setVoiceStatus('Thinking...', 'thinking');

  try {
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');
    formData.append('generate_audio', isAudioOutputEnabled ? 'true' : 'false');
    formData.append('user_name', 'Web Customer');

    const savedEmail = localStorage.getItem('shopnest_customer_email');
    if (savedEmail) {
      formData.append('email', savedEmail);
    }

    const response = await fetch(`${apiBaseUrl}/api/voice/chat`, {
      method: 'POST',
      body: formData
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Voice processing failed.');
    }

    updateVoiceMessageContent(tempUserMsgId, `🎤 "${escapeHtml(data.query)}"`);
    appendVoiceMessage('bot', data.response, data.audio_base64);

    if (isAudioOutputEnabled && data.audio_base64) {
      playVoiceAudio(data.audio_base64);
    } else {
      setVoiceStatus('Ready to listen', 'ready');
    }

  } catch (err) {
    console.error('Voice chat processing error:', err);
    updateVoiceMessageContent(tempUserMsgId, `❌ Error: ${err.message}`);
    setVoiceStatus('Error', 'error');
  } finally {
    if (transcriptBox) transcriptBox.style.display = 'none';
    if (micLabel) micLabel.innerText = 'Click Mic to Speak';
  }
}

// Text & Quick Prompt Query Submission
async function sendQuickVoicePrompt(promptText) {
  const input = document.getElementById('voice-text-input');
  if (input) input.value = promptText;
  await submitVoiceTextQuery();
}

async function submitVoiceTextQuery() {
  const input = document.getElementById('voice-text-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  appendVoiceMessage('user', escapeHtml(text));
  setVoiceStatus('Thinking...', 'thinking');

  try {
    const formData = new FormData();
    formData.append('text_query', text);
    formData.append('generate_audio', isAudioOutputEnabled ? 'true' : 'false');
    formData.append('user_name', 'Web Customer');

    const savedEmail = localStorage.getItem('shopnest_customer_email');
    if (savedEmail) {
      formData.append('email', savedEmail);
    }

    const response = await fetch(`${apiBaseUrl}/api/voice/chat`, {
      method: 'POST',
      body: formData
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Query processing failed.');
    }

    appendVoiceMessage('bot', data.response, data.audio_base64);

    if (isAudioOutputEnabled && data.audio_base64) {
      playVoiceAudio(data.audio_base64);
    } else {
      setVoiceStatus('Ready to listen', 'ready');
    }

  } catch (err) {
    console.error('Voice text query error:', err);
    appendVoiceMessage('bot', `❌ Error retrieving answer: ${err.message}`);
    setVoiceStatus('Error', 'error');
  }
}

// Initialize on Load
window.addEventListener('DOMContentLoaded', () => {
  loadProducts();
});
