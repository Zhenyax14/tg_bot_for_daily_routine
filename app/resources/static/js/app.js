// Adjuntar imagen (panel IA): muestra el nombre del fichero elegido.
document.querySelectorAll('.ai-file input[type=file]').forEach(function (input) {
  input.addEventListener('change', function () {
    var box = input.closest('.ai-file');
    var label = box.querySelector('.ai-file-name');
    var file = input.files && input.files[0];
    box.classList.toggle('has-file', !!file);
    label.textContent = file ? file.name : label.dataset.empty;
  });
});
