export default function EmptyState({ title, description, action }) {
  return (
    <div className="empty-state" role="status">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  );
}
