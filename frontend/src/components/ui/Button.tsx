import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  disabled,
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center font-medium transition-all duration-150 rounded-lg select-none disabled:opacity-40 disabled:cursor-not-allowed';

  const sizeStyles = {
    sm: 'text-xs px-2.5 py-1.5 gap-1.5',
    md: 'text-sm px-3.5 py-2 gap-2',
    lg: 'text-sm px-5 py-2.5 gap-2.5 font-semibold',
  };

  const variantStyles = {
    primary: 'bg-accent text-white hover:bg-accent-hover active:scale-[0.98]',
    secondary: 'bg-studio-panel text-studio-text border border-studio-border hover:bg-studio-raised active:bg-studio-hover shadow-sm',
    ghost: 'bg-transparent text-studio-muted hover:text-studio-text hover:bg-studio-hover active:bg-studio-line',
    danger: 'bg-danger-soft text-danger border border-danger-border hover:bg-danger-soft active:bg-danger-soft',
  };

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
};

export default Button;
