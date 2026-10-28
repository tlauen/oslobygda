/* Progressiv forbetring: vanleg kodefelt fungerer òg utan JavaScript. */
(() => {
  document.querySelectorAll('[data-otp-code]').forEach(original => {
    const label = document.querySelector(`label[for="${original.id}"]`);
    const group = document.createElement('div');
    group.className = 'otp-fields';
    group.setAttribute('role', 'group');
    if (label) {
      label.id ||= `${original.id}-label`;
      group.setAttribute('aria-labelledby', label.id);
    }
    const fields = Array.from({length: 6}, (_, i) => {
      const field = document.createElement('input');
      field.type = 'text';
      field.id = `${original.id}-digit-${i + 1}`;
      field.inputMode = 'numeric';
      field.autocomplete = i === 0 ? 'one-time-code' : 'off';
      field.pattern = '[0-9]';
      field.required = true;
      field.setAttribute('aria-label', `Siffer ${i + 1} av 6`);
      group.append(field);
      return field;
    });
    const sync = () => { original.value = fields.map(field => field.value).join(''); };
    const distribute = (value, index) => {
      const digits = value.replace(/[^0-9]/g, '').slice(0, 6);
      if (!digits) return;
      const start = digits.length === 6 ? 0 : index;
      [...digits].slice(0, 6 - start).forEach((digit, offset) => {
        fields[start + offset].value = digit;
      });
      sync();
      const next = fields[Math.min(start + digits.length, 5)];
      next.focus();
      next.select();
    };
    fields.forEach((field, index) => {
      field.addEventListener('focus', () => field.select());
      field.addEventListener('input', () => {
        const value = field.value;
        field.value = '';
        distribute(value, index);
        sync();
      });
      field.addEventListener('paste', event => {
        const value = event.clipboardData?.getData('text');
        if (value !== undefined) {
          event.preventDefault();
          distribute(value, index);
        }
      });
      field.addEventListener('keydown', event => {
        let next;
        if (event.key === 'Backspace' && !field.value && index > 0) {
          next = fields[index - 1];
          next.value = '';
          sync();
        } else if (event.key === 'ArrowLeft' && index > 0) next = fields[index - 1];
        else if (event.key === 'ArrowRight' && index < 5) next = fields[index + 1];
        if (next) {
          event.preventDefault();
          next.focus();
          next.select();
        }
      });
    });
    const initial = original.value;
    original.type = 'hidden';
    original.required = false;
    original.after(group);
    if (label) label.htmlFor = fields[0].id;
    if (initial) distribute(initial, 0);
    original.form?.addEventListener('reset', () => {
      fields.forEach(field => { field.value = ''; });
      original.value = '';
    });
  });
})();
