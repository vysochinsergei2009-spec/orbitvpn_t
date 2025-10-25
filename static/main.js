// Navbar scroll effect
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
});

// Smooth scroll for anchor links
document.addEventListener('DOMContentLoaded', () => {
    const links = document.querySelectorAll('a[href^="#"]');

    links.forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            if (href !== '#') {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });
});

// Subtle glass orb mouse tracking
document.addEventListener('DOMContentLoaded', () => {
    const orb = document.querySelector('.glass-orb');
    if (!orb) return;

    let mouseX = 0;
    let mouseY = 0;
    let orbX = 0;
    let orbY = 0;

    document.addEventListener('mousemove', (e) => {
        mouseX = (e.clientX - window.innerWidth / 2) / 50;
        mouseY = (e.clientY - window.innerHeight / 2) / 50;
    });

    function animate() {
        orbX += (mouseX - orbX) * 0.05;
        orbY += (mouseY - orbY) * 0.05;

        orb.style.transform = `translate(${orbX}px, ${orbY}px)`;
        requestAnimationFrame(animate);
    }

    animate();
});

// Liquid glass button - cursor following highlight
document.addEventListener('DOMContentLoaded', () => {
    const button = document.querySelector('.cta-button');
    if (!button) return;

    button.addEventListener('mousemove', (e) => {
        const rect = button.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percentage = (x / rect.width) * 100;

        // Move highlight to follow cursor
        const highlight = button.querySelector('::before') || button;
        button.style.setProperty('--mouse-x', `${percentage}%`);
    });

    button.addEventListener('mouseleave', () => {
        button.style.setProperty('--mouse-x', '-30%');
    });
});
