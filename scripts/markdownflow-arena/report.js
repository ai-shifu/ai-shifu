const dialog = document.querySelector('dialog');
const preview = dialog.querySelector('img');
document.querySelectorAll('.zoom').forEach((button) => {
  button.addEventListener('click', () => {
    const image = button.querySelector('img');
    preview.src = image.src;
    preview.alt = image.alt;
    dialog.showModal();
  });
});
dialog.querySelector('.close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', (event) => {
  if (event.target === dialog) dialog.close();
});
