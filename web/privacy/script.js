// Parallax эффект для фона
let ticking = false;
let parallaxStyle = null;

// Создаем style элемент один раз
document.addEventListener('DOMContentLoaded', () => {
    parallaxStyle = document.createElement('style');
    parallaxStyle.id = 'parallax-style';
    document.head.appendChild(parallaxStyle);
});

window.addEventListener('scroll', () => {
    if (!ticking) {
        window.requestAnimationFrame(() => {
            const scrolled = window.pageYOffset;
            const parallaxOffset = scrolled * 0.1; // 10% скорости скролла (медленнее)

            if (parallaxStyle) {
                parallaxStyle.textContent = `body::before { transform: translate3d(0, ${parallaxOffset}px, 0); }`;
            }

            ticking = false;
        });
        ticking = true;
    }
}, { passive: true });

// Intersection Observer для fade-in/out эффектов при скролле
const observerOptions = {
    threshold: 0.15,
    rootMargin: '0px 0px -10% 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            entry.target.classList.remove('hidden');
        } else {
            entry.target.classList.remove('visible');
            entry.target.classList.add('hidden');
        }
    });
}, observerOptions);

// Наблюдаем за всеми анимируемыми элементами
document.addEventListener('DOMContentLoaded', () => {
    const animatedElements = document.querySelectorAll('.nav, .section, .step, .app-list, .important');

    animatedElements.forEach(element => {
        element.classList.add('fade-element');
        observer.observe(element);
    });
});
