// Adjuntar ficheros (panel IA): muestra el nombre de los ficheros elegidos.
document.querySelectorAll('.ai-file input[type=file]').forEach(function (input) {
  input.addEventListener('change', function () {
    var box = input.closest('.ai-file');
    var label = box.querySelector('.ai-file-name');
    var files = input.files ? Array.prototype.map.call(input.files, function (f) { return f.name; }) : [];
    box.classList.toggle('has-file', files.length > 0);
    label.textContent = files.length ? files.join(', ') : label.dataset.empty;
  });
});

// Formularios destructivos (borrar documento): pide confirmacion.
document.querySelectorAll('form[data-confirm]').forEach(function (form) {
  form.addEventListener('submit', function (event) {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
